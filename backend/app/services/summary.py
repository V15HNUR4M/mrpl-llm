from typing import Optional
from app.db.uow import UnitOfWork
from app.core.context_engine.schemas import ContextCandidate
from app.core.model_gateway.gateway import ModelGateway
from app.core.model_gateway.schemas import GenerationRequest, Message as GenMessage

class ConversationSummaryService:
    def __init__(self, uow: UnitOfWork, gateway: ModelGateway):
        self.uow = uow
        self.gateway = gateway
        self.summarization_threshold = 10 # Number of unsummarized messages required to trigger a summary

    async def get_summary_candidate(
        self, conversation_id: str, user_id: str, oldest_recent_seq_num: int
    ) -> Optional[ContextCandidate]:
        """
        Retrieves or generates a summary for a conversation and returns it as a ContextCandidate.
        oldest_recent_seq_num is the sequence number of the oldest message in the recent message window.
        """
        # Ensure conversation exists and user owns it
        conversation = await self.uow.conversations.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            return None

        # Fetch existing summary
        summary = await self.uow.summaries.get_by_conversation_id(conversation_id)
        last_seq = summary.last_sequence_number if summary else 0

        end_seq = oldest_recent_seq_num - 1

        # Fetch unsummarized messages
        unsummarized = await self.uow.messages.list_older_messages(conversation_id, last_seq, end_seq)

        if len(unsummarized) >= self.summarization_threshold:
            # We have enough messages to summarize
            try:
                new_summary_text = await self._generate_summary(summary.content if summary else None, unsummarized)
                
                # Persist summary
                if summary:
                    summary = await self.uow.summaries.update(summary, {
                        "content": new_summary_text,
                        "last_sequence_number": unsummarized[-1].sequence_number
                    })
                else:
                    summary = await self.uow.summaries.create({
                        "conversation_id": conversation_id,
                        "content": new_summary_text,
                        "last_sequence_number": unsummarized[-1].sequence_number
                    })
                
                await self.uow.commit() # Commit the new summary
            except Exception as e:
                # If summarization fails, don't crash and don't corrupt the previous summary.
                print(f"Summarization failed: {e}")
                # Fallback to the existing summary if available
                pass

        if summary:
            return ContextCandidate(
                id=f"summary_{summary.id}",
                type="summary",
                content=summary.content,
                priority=6
            )
            
        return None

    async def _generate_summary(self, previous_summary: Optional[str], new_messages: list) -> str:
        prompt = "Summarize the following conversation history.\n\n"
        if previous_summary:
            prompt += f"Previous Summary:\n{previous_summary}\n\n"
            
        prompt += "New Messages:\n"
        for msg in new_messages:
            role = msg.role.capitalize()
            prompt += f"{role}: {msg.content}\n"
            
        prompt += "\nPlease provide a concise and updated summary incorporating the new messages. Preserve important facts, decisions, and user goals."
        
        from app.core.config import settings
        
        gen_req = GenerationRequest(
            model=settings.DEFAULT_CHAT_MODEL,
            messages=[GenMessage(role="user", content=prompt)]
        )
        
        response = await self.gateway.generate(gen_req)
        return response.text.strip()
