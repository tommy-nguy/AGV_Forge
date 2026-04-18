import json
import jsonschema

def validate_planner_output(planner_json: dict):
    # 1. Validate Base Envelope
    with open('schemas/system2.base.schema.json') as f:
        base_schema = json.load(f)
    jsonschema.validate(instance=planner_json, schema=base_schema)

    # 2. Route và Validate Child Schema
    content_mode = planner_json.get('content_mode')
    if content_mode == 'cinematic_story_video':
        with open('schemas/system2.cinematic_story_video.schema.json') as f:
            child_schema = json.load(f)
    elif content_mode == 'knowledge_explainer_video':
        with open('schemas/system2.knowledge_explainer_video.schema.json') as f:
            child_schema = json.load(f)
    else:
        raise ValueError(f"Unknown content_mode: {content_mode}")

    jsonschema.validate(instance=planner_json, schema=child_schema)
    
    # 3. Sau khi pass 2 bước trên, mới chạy Business Logic Validation (Semantic/Execution)
    # ...

    return True