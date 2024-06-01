from .llm import get_llm
from .character import Character
from .locaitons import Location, LocationStore
from llama_index.core.program import LLMTextCompletionProgram

from llama_index.core.program import LLMTextCompletionProgram
from llama_index.core import PromptTemplate
from tenacity import retry, stop_after_attempt
from pydantic import BaseModel, Field
from typing import Optional, List, Any


class StoryItem(BaseModel):
    "A story item for a D&D campaign."

    name: str = Field(..., description="The name of the story item.")
    details: str = Field(..., description="A description of the story item.")
    completed: bool = Field(
        False, description="Whether the story item has been completed by the party."
    )


class StoryItems(BaseModel):
    items: List[StoryItem] = Field([], description="The story items in the storyline.")

    @classmethod
    @retry(stop=stop_after_attempt(3))
    def generate(cls, storyline):
        example = """\
{
    "name": "Event 1: The Mysterious Letter",
    "details": "The party receives an anonymous letter containing a cryptic message hinting at the location of the Lost Relic. The message leads them to an old library in the city, where they must search for clues and solve riddles to uncover the next lead."
}\
"""
        start_story_item_template = PromptTemplate("""\
You are a dungeion master creating a story item for a D&D quest. \
Here is the storyline you are working on:
Title: {name}
Description: {details}
                                                   
Create 3-5 events that will happen in the storyline if it's followed. \
The final event should be the conclusion of the storyline. \

Answer: \
""").partial_format(name=storyline.name, details=storyline.details, example=example)
        story_item_program = LLMTextCompletionProgram.from_defaults(
            llm=get_llm(), prompt=start_story_item_template, output_cls=StoryItems
        )
        story_items = story_item_program()
        return story_items


class StoryLine(BaseModel):
    "A storyline for a D&D campaign. Contains the overarching story for a one-shot campaign."

    name: str = Field(..., description="The name of the storyline.")
    details: str = Field(..., description="A description of the storyline.")
    completed: bool = Field(
        False, description="Whether the storyline has been completed by the party."
    )

    @classmethod
    @retry(stop=stop_after_attempt(3))
    def generate(cls, character, city, region, locations):
        start_story_template = PromptTemplate("""\
You are a dungeion master creating a storyline for a D&D one-shot campaign. \
Here are the characters in the party: 
{characters}
                                      
The party is currently in the {current_location} of the {region} region. \
Here is the detailed location information:
{locations}
                           
Answer: \
""").partial_format(
            characters=[character],
            current_location=city.name,
            region=region.name,
            locations=locations,
        )
        storyline_program = LLMTextCompletionProgram.from_defaults(
            llm=get_llm(), prompt=start_story_template, output_cls=StoryLine
        )
        storyline = storyline_program()
        return storyline


class StoryLineWithStoryItems(StoryLine):
    items: StoryItems = Field(
        [], title="Items", description="The story items in the storyline."
    )

    @classmethod
    @retry(stop=stop_after_attempt(3))
    def generate(cls, character, city, region, locations):
        storyline = StoryLine.generate(character, city, region, locations)
        items = StoryItems.generate(storyline)
        return cls(name=storyline.name, details=storyline.details, items=items)
