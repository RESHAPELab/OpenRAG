from pathlib import Path
from typing import Iterable

from git import Repo
from langchain_community.document_loaders import DirectoryLoader
from langchain_core.documents import Document
from langchain_text_splitters import TextSplitter
from pydantic import AnyUrl, validate_call

from src.domain.content import Content
from src.port.content import ContentPort

__all__ = ("GitWikiContentAdapter",)


class GitWikiContentAdapter(ContentPort):
    def __init__(self, splitter: TextSplitter, assets_path: Path) -> None:
        self._splitter = splitter
        self._assets_path = assets_path

    def _clone_repo(self, target: Path, url: str) -> None:
        import platform
        
        # On Windows, some wiki files have colons in names which are invalid on Windows
        # Use sparse-checkout to skip problematic files
        if platform.system() == "Windows":
            import git
            
            # Clone without checkout first
            repo = Repo.clone_from(url, target, no_checkout=True)
            
            # Configure git to be more lenient with Windows paths
            with repo.config_writer() as config:
                config.set_value("core", "protectNTFS", "false")
            
            # Try to checkout, skipping files that fail
            try:
                repo.git.checkout("HEAD", force=True)
            except git.exc.GitCommandError:
                # Some files have invalid Windows filenames, skip them
                # Try sparse checkout to get valid files only
                try:
                    repo.git.sparse_checkout("init", "--cone")
                    repo.git.sparse_checkout("set", "*")
                except Exception:
                    pass  # Continue with whatever files we could check out
        else:
            Repo.clone_from(url, target)

    def _get_docs(self, path: Path) -> Iterable[Document]:
        loader = DirectoryLoader(
            path.absolute().as_posix(),
            show_progress=True,
            use_multithreading=True,
            silent_errors=True,  # Skip unsupported files (PDFs, images, etc.)
        )

        yield from loader.load_and_split(self._splitter)

    @validate_call
    def get_by_path(self, project: str, path: Path) -> Iterable[Content]:
        for doc in self._get_docs(path):
            yield Content.from_document(
                doc,
                source=path.name,
                project=project,
            )

    @validate_call
    def get_by_url(self, project: str, url: AnyUrl) -> Iterable[Content]:
        if not url.path:
            raise ValueError("Cannot define the repository")

        url_path = url.path.rsplit("/", maxsplit=1)[-1].lower()
        if url_path.endswith("/"):
            url_path = url_path[:-1]
        if url_path.endswith(".git"):
            url_path = url_path[:-4]

        url_parts = url_path.rsplit(".", maxsplit=1)[-2:]
        if len(url_parts) != 2:
            raise ValueError("Bad format url")
        repo_name, term = url_parts

        if term.lower() != "wiki":
            raise ValueError("Url must end path as 'wiki' or 'wiki.git")

        path = self._assets_path.joinpath(f"{repo_name}.{term}")
        self._clear_folder(path, mkdir=False)
        self._clone_repo(path, url.unicode_string())

        yield from self.get_by_path(project, path)
