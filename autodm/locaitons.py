from llama_index.core.program import LLMTextCompletionProgram
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict, Union
from pathlib import Path
import json
from tenacity import retry, stop_after_attempt
import networkx as nx
import matplotlib.pyplot as plt
from .llm import get_llm

LOCATION_SAVE_PATH = Path('~').expanduser() / '.autodm/location_graph.adjlist'

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
        allowed_children_str = "\n".join(
            [f"{k}: {v}" for k, v in ALLOWED_CHILDREN.items()]
        )
        prompt = f"""Please create a location for a D&D campaign. \
If a parent is passed, please make sure the properties align with the parent location and that the child is not larger than the parent. \
If generating a child, please make sure it follows the allowed child types below:
{allowed_children_str}
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
        allowed_types_str = "Allowed location types: " + ", ".join(ALLOWED_CHILDREN[self.type])
        if not storyline:
            storyline = allowed_types_str
        else:
            storyline = f"{storyline}\n{allowed_types_str}"
        child = Location.generate(
            storyline=storyline,
            parent_name=self.name,
            parent_description=self.description,
        )
        assert (
            child.type in ALLOWED_CHILDREN[self.type]
        ), f"Child type {child.type} not in allowed children. Allowed children are {ALLOWED_CHILDREN[self.type]}"
        child.parent_name = self.name
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
    
class LocationGraph:
    def __init__(self):
        self.graph = nx.Graph()

    def set_current_location(self, location_name: str):
        self.current_location = self[location_name]

    def list_locations(self, type:Optional[str]=None) -> List[str]:
        nodes = [self[i] for i in self.graph.nodes]
        nodes = [node for node in nodes if node.type == type] if type else nodes
        return [node.name for node in nodes]

    def add_location(self, location: Location):
        self.graph.add_node(location.name, **location.model_dump())
        if location.parent_name:
            self.graph.add_edge(location.parent_name, location.name)

    def _node_to_location(self, node: Dict[str, Any]) -> Location:
        return Location(**node)
    
    def _nodes_to_locations(self, nodes: List[Dict[str, Any]]) -> List[Location]:
        return [self._node_to_location(node) for node in nodes]

    def get_children(self, location_name: str):
        nodes = self.graph.nodes
        children = [node for node in nodes if self[node].parent_name == location_name]
        return children
    
    def get_parent(self, location_name: str):
        location = self[location_name].parent_name
        if location is not None:
            return location
        else:
            return "No parent location"

    def get_location(self, location_name: str) -> Optional[Dict[str, str]]:
        if location_name in self.graph:
            node = self.graph.nodes[location_name]
            return self._node_to_location(node)
        return None

    def get_path(self, start_location: str, end_location: str):
        try:
            path = nx.shortest_path(self.graph, start_location, end_location)
            return path
        except nx.NetworkXNoPath:
            return None
        
    def __getitem__(self, name):
        return self._node_to_location(self.graph.nodes[name])
    
    def travel_plan(self, location_name: str) -> Union[str, List[Location]]:
        if location_name not in self.graph:
            return "The location name is unknown. Try creating the location first, then try again."
        paths = self.get_path(self.current_location.name, location_name)
        return f"To reach {location_name} from {paths[0]}, you must travel through the following locations: {','.join(paths[1:-1])}"
        
    def visualize(self):
        plt.figure(figsize=(10, 8))
        pos = nx.spring_layout(self.graph)
        nx.draw(self.graph, pos, with_labels=True, node_size=3000, node_color='skyblue', font_size=10, font_weight='bold')
        node_labels = {node: "\n\n" + data['type'] for node, data in self.graph.nodes(data=True)}
        nx.draw_networkx_labels(self.graph, pos, labels=node_labels, font_size=8, font_color='red')
        plt.title('Location Graph')
        plt.show()

    def save(self, path: Union[str, Path]=LOCATION_SAVE_PATH):
        nx.write_adjlist(self.graph)

    @classmethod
    def load(cls, path: Union[Path, str]=LOCATION_SAVE_PATH):
        graph = nx.read_adjlist("location_graph.adjlist", create_using=nx.DiGraph)
        location_graph = cls()
        location_graph.graph = graph
        return location_graph

@retry(stop=stop_after_attempt(3))
def setup_new_locations():
    """
    Initializes a starting region and city where the game starts.

    Returns: 
        LocationStore: A LocationStore object containing the starting region and city.
    """
    region = Location.generate(type="region")
    city = region.generate_child(type="city")
    locations = LocationGraph()
    locations.add_location(region)
    locations.add_location(city)
    locations.set_current_location(city.name)

    return locations