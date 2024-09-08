from llama_index.llms.ollama import Ollama

class LLMManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LLMManager, cls).__new__(cls)
            # cls._instance.llm = Ollama(model="llama3.1")
            cls._instance.llm = Ollama(model='hermes3')
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