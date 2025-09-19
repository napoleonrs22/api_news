from django.urls import path
from . import  views

urlpatterns = [
    path('',views.CommentListCreateView.as_view(),name='comment-list'),
    path('<int:pk>',views.CommentDetailView.as_view(),name='comment-detail'),
    path('my-comments/',views.MyCommentView.as_view(),name='comment-list'),
    path('post/<int:post_id>/', views.post_comments,name='comment-post'),
    path('<int:comment_id>/replies/',views.comment_replies,name='comment-replies'),
]