"""测试替身（StubClient 等）"""


class StubClient:
    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def embed_batch(self, texts, skip_failures=True):
        return [[1.0, 0.0] for _ in texts]

    async def rerank(self, query, documents, top_n=None):
        top_n = top_n or len(documents)
        return [{"index": i, "relevance_score": 1.0 / (i + 1)} for i in range(min(top_n, len(documents)))]


class StubClientWithFailures(StubClient):
    async def embed_batch(self, texts, skip_failures=True):
        if len(texts) == 1:
            return [None]
        return [None, [1.0, 0.0]]


class StubEmbedClient401:
    def __init__(self):
        self.last_error_status = 401
        self.last_error_message = "auth failed"


class StubClientAuthFailure(StubClient):
    def __init__(self):
        self._embed_client = StubEmbedClient401()

    async def embed(self, texts):
        return None


class StubClientRerankFailure(StubClient):
    async def rerank(self, query, documents, top_n=None):
        return []
