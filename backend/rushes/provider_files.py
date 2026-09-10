def delete_provider_file(client, name: str) -> None:
    from google.genai import errors

    try:
        client.files.delete(name=name)
    except errors.ClientError as error:
        if error.code != 404:
            raise
