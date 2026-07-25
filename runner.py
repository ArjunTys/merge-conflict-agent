from crewai import Crew
from agent import create_merge_conflict_task, get_merge_conflict_agent

def resolve_one_conflict(agent, conflict):
    try:
        task = create_merge_conflict_task(
            agent,
            conflict["filename"],
            conflict["ancestor"],
            conflict["main_version"],
            conflict["incoming_version"],
            conflict["extra_context"],
        )
        crew = Crew(agents=[agent], tasks=[task])
        crew.kickoff()

        resolution = task.output.pydantic
        if resolution is None:
            # the model ran but produced nothing matching the schema
            return None
        return resolution

    except Exception as e:
        # anything went wrong resolving this one conflict:
        # model error, schema validation failure, missing dict key, etc.
        print(f"Failed to resolve conflict in {conflict.get('filename', 'unknown file')}: {e}")
        return None
    

def resolve_all_conflicts(conflicts):
    agent = get_merge_conflict_agent()   
    resolutions = []
    for conflict in conflicts:
        result = resolve_one_conflict(agent, conflict)
        resolutions.append(result)       
    return resolutions