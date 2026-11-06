from django.contrib import admin

from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle


@admin.register(ChessPuzzleCategory)
class ChessPuzzleCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "mate_in", "is_active", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ChessPuzzle)
class ChessPuzzleAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "perspective", "fen", "branch_count", "created_at")
    list_filter = ("category", "perspective")
    search_fields = ("fen", "title")
    readonly_fields = ("position", "solution", "branches", "generation", "created_at")

    @admin.display(description="branches")
    def branch_count(self, obj: ChessPuzzle) -> int:
        return len(obj.branches)


@admin.register(UserChessPuzzle)
class UserChessPuzzleAdmin(admin.ModelAdmin):
    list_display = ("user", "puzzle", "wrong_moves", "hints_used", "updated_at")
    list_filter = ("puzzle__category",)
    raw_id_fields = ("user", "puzzle")
