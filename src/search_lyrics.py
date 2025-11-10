# src/search_lyrics.py
import numpy as np
import faiss
import pickle
from openai import OpenAI

class LyricsSearcher:
    def __init__(self, index_path, meta_path, api_key, emb_model="text-embedding-3-small"):
        self.index = faiss.read_index(index_path)
        with open(meta_path, "rb") as f:
            self.meta = pickle.load(f)  # list[dict]
        self.client = OpenAI(api_key=api_key)
        self.emb_model = emb_model

    def embed(self, text):
        emb = self.client.embeddings.create(model=self.emb_model, input=text).data[0].embedding
        return np.array(emb, dtype="float32")[None, :]  # (1, d)

    def search(self, query, k=5):
        qv = self.embed(query)
        D, I = self.index.search(qv, k)
        hits = []
        for rank, idx in enumerate(I[0]):
            item = dict(self.meta[idx])
            item["rank"] = rank + 1
            item["score_l2"] = float(D[0][rank])
            hits.append(item)
        return hits