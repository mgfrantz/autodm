from llama_index.llms.openai import OpenAI # type: ignore
from llama_index.llms.huggingface import HuggingFaceInferenceAPI # type: ignore
from llama_index.core.output_parsers import PydanticOutputParser # type: ignore
import os

API_BASE = "http://localhost:1234/v1"
API_KEY = "lm-studio"
HF_MODEL = "meta-llama/Meta-Llama-3-70B-Instruct"
# HF_MODEL = "mistralai/Mixtral-8x7B-Instruct-v0.1"
# HF_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"

def get_llm(output_cls=None, temperature=0.7):
    """
    Returns an instance of the OpenAI class for Language Model (LLM) API to call LM Studio.

    Parameters:
        output_cls (optional): The output class for parsing the API response. If not provided, a default parser will be used.

    Returns:
        An instance of the OpenAI class for Language Model (LLM) API.

    """
    kwargs = {
        "temperature": temperature
    }
    if output_cls is not None:
        kwargs['output_parser'] = PydanticOutputParser(output_cls)
    if os.environ.get("HF_TOKEN") is not None:
        return HuggingFaceInferenceAPI(model_name=HF_MODEL, token=os.environ.get("HF_TOKEN"), system_prompt="""You are a helpful assistant to a D&D dungeon master that is an expert at formatting jsons. Always return the correct json format without any additional data. Make sure all json fields are returned like this: {"key":"value"}""", **kwargs)
    else:
        return OpenAI(api_base=API_BASE, api_key=API_KEY, **kwargs)