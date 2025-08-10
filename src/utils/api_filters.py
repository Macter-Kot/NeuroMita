def apply_filter(filter_fn: str, data: dict) -> dict:
    if filter_fn == "filter_generate_content":
        return filter_generate_content(data)
    return data


def filter_generate_content(data: dict) -> dict:
    if 'models' in data:
        filtered_models = []
        for model in data['models']:
            methods = model.get('supportedGenerationMethods', [])
            if 'generateContent' in methods:
                filtered_models.append(model)
        data['models'] = filtered_models
    return data