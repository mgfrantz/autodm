from llama_index.vector_stores.lancedb import LanceDBVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import StorageContext, VectorStoreIndex, Document
from llama_index.core.postprocessor import FixedRecencyPostprocessor

from pydantic import BaseModel, Field
from typing import Optional, List, Any, Union
from pathlib import Path
from datetime import datetime
from pathlib import Path
import torch
from .llm import get_llm

VECTORSTORE_DIR = Path('~').expanduser() / '.autodm/vectorstore'
if not VECTORSTORE_DIR.exists():
    VECTORSTORE_DIR.mkdir(parents=True)
ADVENTURE_LOG_TABLE_NAME = 'adventure_log'

def get_device():
    if torch.backends.mps.is_available():
        return 'mps'
    elif torch.cuda.is_available():
        return 'cuda'
    else:
        return 'cpu'

class AdventureLog:
    def __init__(self, lance_uri=VECTORSTORE_DIR, lance_table=ADVENTURE_LOG_TABLE_NAME):
        self.lance_uri = lance_uri
        self.lance_table = lance_table
        self.storage_context = self._setup_storage_context()
        try:
            self.index = self._setup_index()
        except Exception as e:
            self.index = None
            print("Failed to set up index. Will try again on first log.", e)

    def _setup_storage_context(self):
        return StorageContext.from_defaults(
            vector_store=LanceDBVectorStore(
                uri=str(self.lance_uri), table_name=str(self.lance_table)
            )
        )

    def _setup_index(self, doc_or_docs: Union[Document, List[Document]] = None):
        embed_model = HuggingFaceEmbedding(
            "Alibaba-NLP/gte-base-en-v1.5", device=get_device(), trust_remote_code=True
        )
        if doc_or_docs is not None:
            if not isinstance(doc_or_docs, list):
                doc_or_docs = [doc_or_docs]
            return VectorStoreIndex.from_documents(
                doc_or_docs,
                embed_model=embed_model,
                storage_context=self.storage_context,
            )
        else:
            return VectorStoreIndex.from_vector_store(
                vector_store = self.storage_context.vector_store,
                embed_model=embed_model, 
                storage_context=self.storage_context
            )

    def add_entry(self, entry: str, user: str = "dm"):
        doc = Document(
            text=entry, extra_info={"user": user, "timestamp": str(datetime.now())}
        )
        if self.index is None:
            self.index = self._setup_index(doc)
        else:
            self.index.insert(doc)

    def search(self, query: str, top_k: int = 5):
        postprocessor = FixedRecencyPostprocessor(date_key='timestamp')
        query_engine = self.index.as_query_engine(llm=get_llm(output_cls=str), similarity_top_k=top_k, node_postprocessors=[postprocessor])
        return query_engine.query(query)
    
    def clear(self):
        if input("Are you sure you want to clear the adventure log? (y/n): ").lower() == 'y':
            self.storage_context.vector_store.client.drop_table(self.lance_table)
            self.index = None