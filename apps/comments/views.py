# views.py

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, filters, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

# Импорты для документации
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, inline_serializer
from drf_spectacular.types import OpenApiTypes

# Импорты вашего проекта
from .models import Comment
from .serializers import (
    CommentSerializer,
    CommentDetailSerializer,
    CommentCreateSerializer,
    CommentUpdateSerializer
)
from .permissions import IsAuthorOrReadOnly
from apps.main.models import Post


class CommentListCreateView(generics.ListCreateAPIView):
    """
    GET:
    Возвращает список активных комментариев с возможностью фильтрации и поиска.

    Вы можете фильтровать комментарии по полям `author`, `post` и `parent`.
    Пример: `?post=1&author=2`

    Также доступен поиск по содержимому (`content`) и сортировка.
    Пример: `?search=hello&ordering=-created_at`

    POST:
    Создает новый комментарий.

    Для создания комментария необходимо быть аутентифицированным.
    В теле запроса нужно передать `content` и `post`. Поле `parent` опционально для создания ответа на другой комментарий.
    """
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['author', 'post', 'parent']
    search_fields = ['content']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        return Comment.objects.filter(is_active=True).select_related(
            'author',
            'post',
            'parent',
        )

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CommentCreateSerializer
        return CommentSerializer


class CommentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """

    GET:
    Получение детальной информации о конкретном комментарии по его ID.

    PUT / PATCH:
    Полное или частичное обновление комментария.

    Права на редактирование есть только у автора комментария.

    DELETE:
    "Мягкое" удаление комментария.

    Комментарий не удаляется из базы данных, а лишь помечается как неактивный (`is_active=False`).
    Права на удаление есть только у автора комментария.
    """
    queryset = Comment.objects.filter(is_active=True).select_related('author', 'post')
    permission_classes = [IsAuthorOrReadOnly]

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return CommentUpdateSerializer
        return CommentDetailSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()


class MyCommentView(generics.ListAPIView):
    """
    Возвращает список комментариев, оставленных текущим аутентифицированным пользователем.

    Этот эндпоинт доступен только для залогиненных пользователей.
    Также поддерживает фильтрацию, поиск и сортировку, как и основной список комментариев.
    """
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['post', 'is_active']
    search_fields = ['content']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self):
        # Оставляем исправление для избежания ошибки при генерации схемы
        if getattr(self, 'swagger_fake_view', False):
            return Comment.objects.none()

        return Comment.objects.filter(author=self.request.user).select_related(
            'post', 'parent',
        )

# Вспомогательный сериализатор ТОЛЬКО для документации
class PostInfoSerializer(serializers.Serializer):
    post = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()


@extend_schema(
    summary="Получить все комментарии для поста",
    description="Возвращает корневые комментарии (`parent=None`) для поста с указанным `post_id`...",
    parameters=[
        OpenApiParameter(
            name='post_id',
            description='ID поста, для которого нужно получить комментарии.',
            required=True,
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH
        )
    ],
    responses={
        200: inline_serializer( # <-- ИСПОЛЬЗУЕМ inline_serializer
            name='PostCommentsResponse',
            fields={
                'post': PostInfoSerializer(),
                'comments': CommentSerializer(many=True),
                'comments_count': serializers.IntegerField()
            }
        ),
        404: OpenApiResponse(description="Пост с указанным ID не найден или не опубликован.")
    }
)
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def post_comments(request, post_id):
    post = get_object_or_404(Post, id=post_id, status='published')

    comments = Comment.objects.filter(post=post, parent=None, is_active=True).select_related('author').prefetch_related('replies_author').order_by(
        '-created_at',)
    serializer = CommentSerializer(comments, many=True, context={'request': request})
    return Response({
        'post': {
            'post': post.id,
            'title': post.title,
            'slug': post.slug
        },
        'comments': serializer.data,
        'comments_count': comments.filter(is_active=True).count(),
    })


@extend_schema(
    summary="Получить ответы на комментарий",
    description="Возвращает все дочерние комментарии (ответы) для родительского комментария...",
    parameters=[
        OpenApiParameter(name='comment_id', type=OpenApiTypes.INT, location=OpenApiParameter.PATH, required=True)
    ],
    responses={
        200: inline_serializer( # <-- ИСПОЛЬЗУЕМ inline_serializer
            name='CommentRepliesResponse',
            fields={
                'parent_comment': CommentSerializer(),
                'replies': CommentSerializer(many=True),
                'replies_count': serializers.IntegerField()
            }
        ),
        404: OpenApiResponse(description="Родительский комментарий не найден.")
    }
)
@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def comment_replies(request, comment_id):
    parent_comment = get_object_or_404(Comment, id=comment_id, is_active=True)

    replies = Comment.objects.filter(
        parent=parent_comment,
        is_active=True,
    ).select_related(
        'author',).order_by('created_at')

    serializer = CommentSerializer(replies, many=True, context={'request': request})

    return Response({
        'parent_comment': CommentSerializer(parent_comment, context={'request': request}).data,
        'replies': serializer.data,
        'replies_count': replies.count(),
    })