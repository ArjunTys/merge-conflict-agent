import json


def write_resolutions_to_json(resolutions, filepath="resolutions.json"):
    output = []

    for i, resolution in enumerate(resolutions):
        if resolution is None:
            # this conflict failed to resolve -- record it so it's visible,
            # not silently dropped
            output.append({
                "conflict_index": i,
                "error": "resolution failed",
            })
        else:
            # convert the Pydantic object into a plain dict (JSON-able),
            # and tag it with its index so it lines up with the input order
            record = resolution.model_dump()
            record["conflict_index"] = i
            output.append(record)

    # write the whole list to the file as pretty-printed JSON
    with open(filepath, "w") as f:
        json.dump(output, f, indent=2)

    return filepath

