from dotenv import load_dotenv
load_dotenv()

from llama_index.llms.ollama import Ollama
from llama_index.llms.gemini import Gemini
from llama_index.core.program import LLMTextCompletionProgram
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from pydantic import BaseModel
from llama_index.core.llms import LLM

class LLMManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMManager, cls).__new__(cls)
            
            # Uncomment the model you want to use
            # cls._instance.llm = Ollama(model="llama3.1")
            # cls._instance.llm = Ollama(model='hermes3')
            # cls._instance.llm = Ollama(model='mistral-nemo')
            
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

llm_manager = LLMManager()

def get_llm() -> LLM:
    return llm_manager.get_llm()

def complete(prompt: str) -> str:
    llm = get_llm()
    response = llm.complete(prompt)
    return response.text

def complete_pydantic(prompt: str, schema: BaseModel) -> str:
    prompt_template_str = f"""\
Generate an example {schema.__name__}, following the structure defined by the Pydantic model.
Use the following context as inspiration: {prompt}
"""
    program = LLMTextCompletionProgram.from_defaults(
        output_cls=schema,
        prompt_template_str=prompt_template_str,
        llm=get_llm(),
        verbose=True,
    )
    
    response = program()
    return response