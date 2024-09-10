from typing import List, Dict
from datetime import datetime
import json
from pathlib import Path
from operator import itemgetter

from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.docstore.document import Document
from langchain.text_splitter import CharacterTextSplitter

class History:
    """
    A class to manage the history of interactions between the agent and the user.
    
    This class provides methods to log new interactions and retrieve past context
    using vector search capabilities.
    """

    def __init__(self):
        """
        Initialize the History object.
        """
        self.config_dir = Path.home() / ".autodm"
        self.config_dir.mkdir(exist_ok=True)
        self.history_file = self.config_dir / "history.json"
        self.index_file = self.config_dir / "faiss_index"
        
        self.history: List[Dict] = self._load_history()
        self.embeddings = HuggingFaceEmbeddings()
        self.index = self._load_or_create_index()

    def _load_history(self) -> List[Dict]:
        """Load the history from the JSON file."""
        if self.history_file.exists():
            with open(self.history_file, 'r') as f:
                return json.load(f)
        return []

    def _save_history(self):
        """Save the current history to the JSON file."""
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)

    def _load_or_create_index(self) -> FAISS:
        """Load existing FAISS index or create a new one."""
        if self.index_file.exists():
            return FAISS.load_local(str(self.index_file), self.embeddings)
        return FAISS.from_documents([], self.embeddings)

    def add_entry(self, role: str, content: str):
        """
        Add a new entry to the history and update the vector index.

        Args:
        role (str): The role of the speaker (e.g., 'user', 'agent').
        content (str): The content of the message.

        Example:
        >>> history = History()
        >>> history.add_entry('user', 'I want to search the room.')
        >>> history.add_entry('agent', 'You find a dusty old book on the shelf.')
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content
        }
        self.history.append(entry)
        self._save_history()

        # Update vector index
        doc = Document(page_content=f"{role}: {content}", metadata={"timestamp": entry["timestamp"]})
        self.index.add_documents([doc])
        self.index.save_local(str(self.index_file))

    def get_recent_context(self, n: int = 5) -> List[Dict]:
        """
        Retrieve the n most recent entries from the history.

        Args:
        n (int): The number of recent entries to retrieve.

        Returns:
        List[Dict]: A list of the n most recent history entries.

        Example:
        >>> history = History()
        >>> recent_context = history.get_recent_context(3)
        >>> for entry in recent_context:
        ...     print(f"{entry['role']}: {entry['content']}")
        """
        return self.history[-n:]

    def search_history(self, query: str, k: int = 5) -> List[Dict]:
        """
        Search the history for entries similar to the given query using vector search.

        Args:
        query (str): The search term to look for in the history.
        k (int): The number of results to return.

        Returns:
        List[Dict]: A list of history entries that are most similar to the query, sorted by timestamp.

        Example:
        >>> history = History()
        >>> results = history.search_history("dragon attack", k=3)
        >>> for entry in results:
        ...     print(f"{entry['timestamp']} - {entry['role']}: {entry['content']}")
        """
        results = self.index.similarity_search(query, k=k)
        entries = [
            {
                "role": doc.page_content.split(":")[0],
                "content": ":".join(doc.page_content.split(":")[1:]).strip(),
                "timestamp": doc.metadata["timestamp"]
            }
            for doc in results
        ]
        # Sort the entries by timestamp
        return sorted(entries, key=itemgetter('timestamp'))