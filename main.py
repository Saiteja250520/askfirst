import os
import uuid
import logging
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

# Import database models and settings
from database import init_db, get_db, Thread, Message, Memory

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("askfirst-backend")

load_dotenv()

# Initialize Database
init_db()

app = FastAPI(title="AskFirst Health AI Backend", version="1.0")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schemas
class ThreadCreate(BaseModel):
    title: Optional[str] = None

class ThreadResponse(BaseModel):
    id: str
    title: str
    created_at: str

    class Config:
        from_attributes = True

class MessageCreate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    id: int
    thread_id: str
    role: str
    content: str
    created_at: str

    class Config:
        from_attributes = True

class MemoryResponse(BaseModel):
    key: str
    value: str

# LLM Client Factory / Routing
def get_llm_client_and_provider():
    """
    Detects which API keys are configured in the environment and returns
    the provider name along with a function to generate content.
    """
    provider = os.getenv("LLM_PROVIDER", "").lower()
    
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    # Auto-detect if provider not explicitly set
    if not provider:
        if gemini_key:
            provider = "gemini"
        elif openai_key:
            provider = "openai"
        elif groq_key:
            provider = "groq"
        else:
            raise RuntimeError("No LLM API keys found in the environment. Please set GEMINI_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY.")
            
    logger.info(f"Using LLM Provider: {provider}")
    
    if provider == "gemini":
        if not gemini_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set.")
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        
        def generate_gemini(prompt: str, history: List[dict] = None) -> str:
            # Reconstruct system instruction and history
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Simple content assembly for Gemini API
            full_prompt = ""
            if history:
                for msg in history:
                    role_label = "User" if msg["role"] == "user" else "Assistant"
                    full_prompt += f"{role_label}: {msg['content']}\n"
            
            full_prompt += f"User: {prompt}\nAssistant:"
            
            response = model.generate_content(full_prompt)
            return response.text
            
        return "gemini", generate_gemini
        
    elif provider == "openai":
        if not openai_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        
        def generate_openai(prompt: str, history: List[dict] = None) -> str:
            messages = []
            if history:
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            return response.choices[0].message.content
            
        return "openai", generate_openai
        
    elif provider == "groq":
        if not groq_key:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY is not set.")
        from openai import OpenAI
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=groq_key)
        
        def generate_groq(prompt: str, history: List[dict] = None) -> str:
            messages = []
            if history:
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=messages
            )
            return response.choices[0].message.content
            
        return "groq", generate_groq
        
    else:
        raise HTTPException(status_code=500, detail=f"Unsupported LLM provider: {provider}")

# Universal Memory Logic
def get_universal_memory(db: Session) -> str:
    memory_record = db.query(Memory).filter(Memory.key == "universal_profile").first()
    if not memory_record or not memory_record.value.strip():
        return "No personal details or medical history remembered yet."
    return memory_record.value

def update_universal_memory_task(db_session_factory, user_msg: str, ai_msg: str):
    """
    Background worker that updates the universal memory based on the latest chat exchange.
    Uses a fresh DB session since it runs in the background.
    """
    db = db_session_factory()
    try:
        existing_memory = get_universal_memory(db)
        
        # We need a call to the LLM to merge and extract new facts
        _, generate_fn = get_llm_client_and_provider()
        
        merge_prompt = f"""You are a professional memory extraction system for a personalized health app.
Here is the existing profile of permanent facts we know about the user:
---
{existing_memory}
---
Here is the latest chat interaction:
User: {user_msg}
Assistant: {ai_msg}

Your task:
1. Extract new permanent facts about the user (such as their name, age, physical symptoms, diagnosed chronic diseases, lifestyle patterns, dietary preferences, or medications). Ignore temporary details or casual conversational fillers.
2. Merge these new facts into the existing profile. Keep the profile structured, concise, and bulleted.
3. If the user corrected any existing information, update the profile to reflect the latest correct detail.
4. If no new long-term facts were shared, repeat the existing profile exactly.
5. Output ONLY the updated profile. Do not add conversational filler or markdown notes (like "Here is the updated profile"). Just output the plain text of the facts.
"""
        updated_memory = generate_fn(merge_prompt, history=None).strip()
        
        # Update or insert into SQLite
        memory_record = db.query(Memory).filter(Memory.key == "universal_profile").first()
        if not memory_record:
            memory_record = Memory(key="universal_profile", value=updated_memory)
            db.add(memory_record)
        else:
            memory_record.value = updated_memory
        db.commit()
        logger.info("Universal memory successfully updated.")
    except Exception as e:
        logger.error(f"Failed to update universal memory: {e}")
        db.rollback()
    finally:
        db.close()

# API Endpoints

@app.post("/threads", response_model=ThreadResponse)
def create_thread(thread_data: ThreadCreate, db: Session = Depends(get_db)):
    thread_id = str(uuid.uuid4())
    title = thread_data.title if thread_data.title else f"Conversation {thread_id[:8]}"
    
    db_thread = Thread(id=thread_id, title=title)
    db.add(db_thread)
    db.commit()
    db.refresh(db_thread)
    
    # Format dates to string
    return ThreadResponse(
        id=db_thread.id,
        title=db_thread.title,
        created_at=db_thread.created_at.isoformat()
    )

@app.get("/threads", response_model=List[ThreadResponse])
def get_threads(db: Session = Depends(get_db)):
    threads = db.query(Thread).order_by(Thread.created_at.desc()).all()
    return [
        ThreadResponse(
            id=t.id,
            title=t.title,
            created_at=t.created_at.isoformat()
        ) for t in threads
    ]

@app.delete("/threads/{thread_id}")
def delete_thread(thread_id: str, db: Session = Depends(get_db)):
    db_thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not db_thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    db.delete(db_thread)
    db.commit()
    return {"message": f"Thread {thread_id} deleted successfully"}

@app.get("/threads/{thread_id}/messages", response_model=List[MessageResponse])
def get_messages(thread_id: str, db: Session = Depends(get_db)):
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    messages = db.query(Message).filter(Message.thread_id == thread_id).order_by(Message.created_at.asc()).all()
    return [
        MessageResponse(
            id=m.id,
            thread_id=m.thread_id,
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat()
        ) for m in messages
    ]

@app.post("/threads/{thread_id}/messages", response_model=MessageResponse)
def post_message(
    thread_id: str, 
    msg_data: MessageCreate, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    # Verify thread exists
    thread = db.query(Thread).filter(Thread.id == thread_id).first()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # 1. Save user message to Database
    user_message = Message(thread_id=thread_id, role="user", content=msg_data.content)
    db.add(user_message)
    db.commit()
    
    # 2. Get past thread history for context
    history_records = db.query(Message).filter(Message.thread_id == thread_id).order_by(Message.created_at.asc()).all()
    
    # Format history for LLM client
    history = [{"role": record.role, "content": record.content} for record in history_records[:-1]] # exclude latest user message
    
    # 3. Retrieve Universal Memory
    universal_mem = get_universal_memory(db)
    
    # 4. Construct System Instruction injecting Universal Memory
    system_instruction = f"""You are AskFirst, a premium and clinically-grounded health and wellness AI assistant. 
You provide clear, accurate, and non-alarmist health clarity. 

Universal Memory Profile:
---
Below are the persistent facts/memory you have collected about this user across all previous chat threads:
{universal_mem}
---
IMPORTANT RULES:
1. Always keep the user's persistent profile (above) in mind when answering. If they tell you they have Diabetes, Asthma, or a specific age, treat this as clinical context for all triage questions.
2. If the user introduces themselves or shares new details, acknowledge it naturally.
3. Be professional, structured, and compassionate. Do not give official diagnostic prescriptions, but provide clear, structured triage advice.
"""

    # Assemble full prompt with system instruction
    full_prompt = f"{system_instruction}\n\nUser's current query: {msg_data.content}"
    
    # 5. Call LLM
    try:
        _, generate_fn = get_llm_client_and_provider()
        ai_response_text = generate_fn(full_prompt, history=history)
    except Exception as e:
        logger.error(f"Error calling LLM: {e}")
        # Clean up database if LLM fails
        db.delete(user_message)
        db.commit()
        raise HTTPException(status_code=500, detail=f"LLM API call failed: {str(e)}")
        
    # 6. Save assistant message to Database
    assistant_message = Message(thread_id=thread_id, role="assistant", content=ai_response_text)
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    
    # 7. Update Thread Title automatically if it was default
    if thread.title.startswith("Conversation "):
        # Use first 6 words of user message as title
        words = msg_data.content.split()
        new_title = " ".join(words[:6]) + ("..." if len(words) > 6 else "")
        thread.title = new_title
        db.commit()

    # 8. Trigger background task to update Universal Memory asynchronously
    # We pass SessionLocal factory so it can create its own DB transaction
    background_tasks.add_task(
        update_universal_memory_task, 
        SessionLocal, 
        msg_data.content, 
        ai_response_text
    )
    
    return MessageResponse(
        id=assistant_message.id,
        thread_id=assistant_message.thread_id,
        role=assistant_message.role,
        content=assistant_message.content,
        created_at=assistant_message.created_at.isoformat()
    )

@app.get("/memory", response_model=MemoryResponse)
def get_memory(db: Session = Depends(get_db)):
    mem_val = get_universal_memory(db)
    return MemoryResponse(key="universal_profile", value=mem_val)

@app.post("/memory/reset")
def reset_memory(db: Session = Depends(get_db)):
    memory_record = db.query(Memory).filter(Memory.key == "universal_profile").first()
    if memory_record:
        memory_record.value = ""
        db.commit()
    return {"message": "Universal memory reset successfully"}
