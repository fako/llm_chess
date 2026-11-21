from django.contrib import admin

from puzzles.models import ChessPuzzle, ChessPuzzleCategory, UserChessPuzzle


@admin.register(ChessPuzzleCategory)
class ChessPuzzleCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "goal", "mate_in", "model", "effort", "is_active", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ChessPuzzle)
class ChessPuzzleAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "perspective", "fen", "model", "effort", "created_at")
    list_filter = ("category", "perspective", "model", "effort")
    search_fields = ("fen", "title")
    readonly_fields = ("position", "solution", "generation", "created_at")


@admin.register(UserChessPuzzle)
class UserChessPuzzleAdmin(admin.ModelAdmin):
    list_display = ("user", "puzzle", "solved_at", "wrong_moves", "hints_used", "updated_at")
    list_filter = ("puzzle__category",)
    raw_id_fields = ("user", "puzzle")
