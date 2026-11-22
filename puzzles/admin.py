from django.contrib import admin

from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle
from puzzles.tags import TAGS


class TagFilter(admin.SimpleListFilter):
    title = "tag"
    parameter_name = "tag"

    def lookups(self, request, model_admin):
        return [(slug, slug) for slug in TAGS]

    def queryset(self, request, queryset):
        return queryset.filter(tags__contains=[self.value()]) if self.value() else queryset


@admin.register(ChessPuzzleCategory)
class ChessPuzzleCategoryAdmin(admin.ModelAdmin):
    list_display = ("name_en", "name_nl", "slug", "goal", "mate_in", "model", "effort", "is_active", "order")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(ChessPuzzle)
class ChessPuzzleAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "perspective", "title_en", "tag_list", "model", "effort", "created_at")
    list_filter = ("category", "perspective", TagFilter, "model", "effort")
    search_fields = ("fen", "title_en", "title_nl")
    readonly_fields = ("position", "tags", "solution", "generation", "created_at")

    @admin.display(description="tags")
    def tag_list(self, puzzle: ChessPuzzle) -> str:
        return ", ".join(puzzle.tags)


@admin.register(UserChessPuzzle)
class UserChessPuzzleAdmin(admin.ModelAdmin):
    list_display = ("user", "puzzle", "solved_at", "wrong_moves", "hints_used", "updated_at")
    list_filter = ("puzzle__category",)
    raw_id_fields = ("user", "puzzle")
