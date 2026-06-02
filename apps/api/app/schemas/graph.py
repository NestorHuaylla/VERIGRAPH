from pydantic import BaseModel, ConfigDict


class GraphNode(BaseModel):
    id: str
    label: str
    type: str


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str
    evidence: dict


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class GraphMetrics(BaseModel):
    entity_id: str
    degree: int
    incoming: int
    outgoing: int


class Neo4jSyncResponse(BaseModel):
    entities_synced: int
    relations_synced: int
    constraints_ensured: int


class GraphProjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    graph_name: str
    node_count: int
    relationship_count: int
    created: bool


class GraphEntityScore(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    label: str
    type: str
    score: float


class GraphScoresResponse(BaseModel):
    items: list[GraphEntityScore]


class GraphCommunityMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_id: str
    label: str
    type: str


class GraphCommunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    community_id: int
    size: int
    members: list[GraphCommunityMember]


class GraphCommunitiesResponse(BaseModel):
    communities: list[GraphCommunityResponse]
