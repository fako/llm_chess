"""
The workspace's own invoke namespace.
"""
from invoke import Collection, Context, task


@task(name="build_tailwind")
def build_tailwind(ctx: Context) -> None:
    """
    Run tailwindcss to create the stylesheet.
    """
    ctx.run("npx tailwindcss -i ./web/tailwind/main.css -o ./web/static/css/tailwind.build.css --minify", echo=True)


@task(name="build_statics", pre=[build_tailwind])
def build_statics(ctx: Context) -> None:
    """
    Run collectstatic to expose static files to Nginx.
    """
    ctx.run("venv/bin/python manage.py collectstatic --noinput", echo=True)


web_collection = Collection("web", build_tailwind, build_statics)

namespace = Collection(web_collection)
