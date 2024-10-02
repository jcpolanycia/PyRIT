# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

from pathlib import Path
from typing import Optional

from pyrit.common.path import DATASETS_PATH
from pyrit.memory import MemoryInterface, DuckDBMemory
from pyrit.models import PromptRequestPiece, Score, PromptTemplate
from pyrit.models.score import UnvalidatedScore
from pyrit.prompt_target import PromptChatTarget
from pyrit.score.scorer import Scorer

REFUSAL_SCORE_SYSTEM_PROMPT = Path(DATASETS_PATH, "score", "refusal.yaml").resolve()


class SelfAskRefusalScorer(Scorer):
    """A self-ask scorer detects a refusal."""

    def __init__(
        self,
        *,
        chat_target: PromptChatTarget,
        memory: MemoryInterface = None,
    ) -> None:

        self.scorer_type = "true_false"

        self._prompt_target = chat_target
        self._memory = memory if memory else DuckDBMemory()
        # Ensure _prompt_target uses the same memory interface as the scorer.
        if self._prompt_target:
            self._prompt_target._memory = self._memory
        self._system_prompt = (PromptTemplate.from_yaml_file(REFUSAL_SCORE_SYSTEM_PROMPT)).template

    async def score_async(self, request_response: PromptRequestPiece, *, task: Optional[str] = None) -> list[Score]:
        """Scores the prompt and determines whether the response is a refusal.

        Args:
            request_response (PromptRequestPiece): The piece to score.
            task (str): The task based on which the text should be scored (the original attacker model's objective).

        Returns:
            list[Score]: The request_response scored.
        """
        self.validate(request_response, task=task)

        if task:
            prompt_value = (
                f"conversation_objective: {task}\nresponse_to_evaluate_input: {request_response.converted_value}"
            )
        else:
            prompt_value = f"response_to_evaluate_input: {request_response.converted_value}"

        unvalidated_score: UnvalidatedScore = await self._score_value_with_llm(
            prompt_target=self._prompt_target,
            system_prompt=self._system_prompt,
            prompt_request_value=prompt_value,
            prompt_request_data_type=request_response.converted_value_data_type,
            scored_prompt_id=request_response.id,
            category="refusal",
            task=task,
        )

        score = unvalidated_score.to_score(score_value=unvalidated_score.raw_score_value)

        self._memory.add_scores_to_memory(scores=[score])
        return [score]

    def validate(self, request_response: PromptRequestPiece, *, task: Optional[str] = None) -> None:
        if request_response.converted_value_data_type != "text":
            raise ValueError("This scorer only supports text data types.")