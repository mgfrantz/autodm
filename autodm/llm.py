from dotenv import load_dotenv
load_dotenv()

from llama_index.llms.ollama import Ollama
from llama_index.llms.gemini import Gemini
from google.generativeai.types import HarmCategory, HarmBlockThreshold

class LLMManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMManager, cls).__new__(cls)
            
            # Uncomment the model you want to use
            # cls._instance.llm = Ollama(model="llama3.1")
            # cls._instance.llm = Ollama(model='hermes3')
            
            # Gemini model with all safety settings set to BLOCK_NONE
            cls._instance.llm = Gemini(
                model='models/gemini-1.5-flash',
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
        return cls._instance

    @classmethod
    def get_llm(cls):
        return cls().llm

    @classmethod
    def complete(cls, prompt: str) -> str:
        return cls().llm.complete(prompt).text

llm_manager = LLMManager()

def get_llm():
    return llm_manager.get_llm()

def complete(prompt: str) -> str:
    return llm_manager.complete(prompt)