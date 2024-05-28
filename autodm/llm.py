from llama_index.llms.openai import OpenAI # type: ignore
from llama_index.core.output_parsers import PydanticOutputParser # type: ignore

API_BASE = "http://localhost:1234/v1"
API_KEY = "lm-studio"


def get_llm(output_cls=None):
    """
    Returns an instance of the OpenAI class for Language Model (LLM) API to call LM Studio.

    Parameters:
        output_cls (optional): The output class for parsing the API response. If not provided, a default parser will be used.

    Returns:
        An instance of the OpenAI class for Language Model (LLM) API.

    """
    if output_cls is None:
        parser = PydanticOutputParser(output_cls)
        return OpenAI(api_base=API_BASE, api_key=API_KEY, output_parser=parser, temperature=0.7)
    else:
        return OpenAI(api_base=API_BASE, api_key=API_KEY, temperature=0.7)
