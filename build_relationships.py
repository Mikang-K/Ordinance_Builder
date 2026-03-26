from pipeline.loaders.neo4j_loader import Neo4jLoader
with Neo4jLoader() as loader:
    loader.build_superior_to_relationships()
    loader.build_similar_to_relationships()
    loader.build_based_on_relationships()
