from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class StaticStorage(ManifestStaticFilesStorage):
    """
    Serves static files under a name with a content hash, so browsers fetch a file again whenever it changes.
    A file that is missing from the manifest falls back to its plain name instead of failing the page,
    which is how static files were served before hashing.
    Hashed names are used in DEBUG too, because Nginx serves the collected files in every installation.
    """
    manifest_strict = False

    def stored_name(self, name: str) -> str:
        try:
            return super().stored_name(name)
        except ValueError:
            return name

    def url(self, name: str, force: bool = False) -> str:
        return super().url(name, force=True)
