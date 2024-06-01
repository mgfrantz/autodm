from llama_index.core.program import LLMTextCompletionProgram
from pydantic import BaseModel, Field
from typing import Optional, List, Any
import json
from tenacity import retry, stop_after_attempt
from .llm import get_llm

LOCATION_TYPES = [
    "region",
    "city",
    "road",
    "dungeon",
    "wilderness",
    "building",
    "room",
]

ALLOWED_CHILDREN = {
    "region": ["city", "road", "dungeon", "wilderness"],
    "city": ["building", "road"],
    "building": ["room"],
    "dungeon": ["room"],
    "wilderness": ["road"],
    "road": ["building"],
    "room": [],
}


class Location(BaseModel):
    """
    Represents a location in a D&D campaign.

    Attributes:
        type (str): The type of the location.
        name (str): The name of the location.
        description (str): A description of the location.
        parent_name (str, optional): The name of the parent location of this location.
        parent_description (str, optional): The description of the parent location of this location.
    """

    type: str = Field(
        ...,
        title="The type of the location",
        description=f"The type of the location, one of {', '.join(LOCATION_TYPES)}",
    )
    name: str = Field(
        ..., title="The name of the location", description="The name of the location"
    )
    description: str = Field(
        ...,
        title="The description of the location",
        description="A description of the location.",
    )
    parent_name: Optional[str] = Field(
        None,
        title="The parent location",
        description="The name of the parent location of this location.",
    )
    parent_description: Optional[str] = Field(
        None,
        title="The parent location description",
        description="The description of the parent location of this location.",
    )

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Location(name={self.name}, type={self.type}, description={self.description}, parent_name={self.parent_name}"

    @classmethod
    def generate(self, storyline: str = None, **kwargs):
        """
        Generates a new location for a D&D campaign.

        Args:
            storyline (str, optional): The storyline the location should fit in with.
            **kwargs: Additional properties for the location.

        Returns:
            Location: The generated location.

        Example:
            location = Location.generate(type="region")
        """
        if "parent_name" not in kwargs and "type":
            kwargs["type"] = "region"
        kwgs = "\n".join([f"{k}: {v}" for k, v in kwargs.items()])
        prompt = f"""Please create a location for a D&D campaign. \
If a parent is passed, please make sure the properties align with the parent location and that the child is not larger than the parent. \
For example, a child of a region should be a city, road, dungeon, or wilderness; \
the child of a city should be a building or a road; and the child of a building should be a room. \
Make sure the location has the following properties: 
{kwgs}"""

        if storyline is not None:
            story_instructions = f"The location should also fit in with the following storyline: {storyline}"
            prompt = f"{prompt}\n{story_instructions}"

        program = LLMTextCompletionProgram.from_defaults(
            prompt_template_str=prompt, output_cls=Location, llm=get_llm()
        )
        return program()

    @retry(stop=stop_after_attempt(3))
    def generate_child(self, storyline: str = None, **kwargs):
        """
        Generates a child location for the current location.

        Args:
            storyline (str, optional): The storyline the child location should fit in with.
            **kwargs: Additional properties for the child location.

        Returns:
            Location: The generated child location.

        Example:
            child_location = location.generate_child(storyline="You leave the tavern and enter a dark alleyway.")
        """
        child = Location.generate(
            storyline=storyline,
            parent_name=self.name,
            parent_description=self.description,
        )
        assert (
            child.type in ALLOWED_CHILDREN[self.type]
        ), f"Child type {child.type} not in allowed children. Allowed children are {ALLOWED_CHILDREN[self.type]}"
        return child


class LocationStore(dict):
    def __init__(self, current: Location, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current = current

    def get_parent(self, location: Location):
        return self[location.parent_name]

    def get_children(self, location: Location):
        return [loc for loc in self.values() if loc.parent_name == location.name]

    def get_siblings(self, location: Location):
        return self.get_children(self.get_parent(location))

    def add(self, location: Location):
        if location.name in self:
            raise ValueError(
                f"Location with name {location.name} already exists in the store."
            )
        self[location.name] = location

    def set_current(self, location: Location):
        self.current = location

    @classmethod
    def new(cls, storyline: str = None):
        location = Location.generate(storyline=storyline)

    def save(self, filename: str = "locations.json"):
        d = {k: v.model_dump() for k, v in self.items()}
        d["current"] = self.current.name
        with open(filename, "w") as f:
            json.dump(d, f)

    @classmethod
    def load(cls, filename: str = "locations.json"):
        with open(filename, "r") as f:
            d = json.load(f)
            current_name = d.pop("current")
        locations = {k: Location(**v) for k, v in d.items()}
        current = locations[current_name]
        return cls(current=current, **locations)

@retry(stop=stop_after_attempt(3))
def setup_new_locations():
    """
    Initializes a starting region and city where the game starts.

    Returns: 
        LocationStore: A LocationStore object containing the starting region and city.
    """
    region = Location.generate(type="region")
    locations = LocationStore(region, **{region.name: region})

    city = locations.current.generate_child(type="city")
    while city.type != "city":
        city = locations.current.generate_child(type="city")
    locations.add(city)
    locations.set_current(city)

    return locations