from rest_framework import serializers

from .models import Commit


class CommitSerializer(serializers.ModelSerializer):
    author_display = serializers.SerializerMethodField()
    deliverable_title = serializers.SerializerMethodField()

    class Meta:
        model = Commit
        fields = (
            "id",
            "sha",
            "message",
            "url",
            "committed_at",
            "author_name",
            "author_email",
            "github_username",
            "author",
            "author_display",
            "deliverable",
            "deliverable_title",
        )
        read_only_fields = fields

    def get_author_display(self, obj):
        return str(obj.author) if obj.author else None

    def get_deliverable_title(self, obj):
        return obj.deliverable.title if obj.deliverable else None
