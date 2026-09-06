import asyncio
from app.main import app, lifespan
from app.core.rag.schemas import RetrievalQuery
from app.core.evaluation.corpus import ensure_evaluation_corpus_indexed
from app.db.database import AsyncSessionLocal
from app.db.models import User
from sqlalchemy import select

async def main():
    async with lifespan(app):
        rag = app.state.rag_service
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(User.id).limit(1))
            user_id = res.scalar_one()

        print(f"Using owner user_id: {user_id}")
        doc_ids = await ensure_evaluation_corpus_indexed(rag, owner_id=user_id)
        print("Indexed docs:", doc_ids)

        # Now search with that user_id
        q = RetrievalQuery(query="What was the bearing vibration reading recorded for Pump P204?", top_k=5, owner_id=user_id)
        results = await rag.search_documents(q)
        print(f"Retrieved {len(results)} results:")
        for r in results:
            print(" - doc_id:", r.document_id, "filename:", r.filename, "content:", r.content[:60])

if __name__ == "__main__":
    asyncio.run(main())
