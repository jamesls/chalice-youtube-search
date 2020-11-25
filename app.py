import os
from datetime import datetime, timedelta
from functools import cached_property
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

import boto3
from chalice import Chalice, Rate
from apiclient.discovery import build


app = Chalice(app_name='youtube-searcher')
CLIENT = None
SSM_PARAM_NAME = '/youtube-searcher/api-key'
DEFAULT_SUBSCRIBERS = 100
YOUTUBE_API_KEY = None
REPORT_EMAIL_ADDRESS = os.environ.get('REPORT_EMAIL_ADDRESS', '')
SEARCH_TERMS = [
    s.strip() for s in os.environ.get('REPORT_SEARCH_TERMS', '').split(',')
]


@dataclass
class VideoResult:
    title: str
    description: str
    channel_id: str
    published_at: str
    video_id: str

    @property
    def video_url(self) -> str:
        return f'https://www.youtube.com/watch?v={self.video_id}'

    @property
    def channel_url(self) -> str:
        return f'https://www.youtube.com/channel/{self.channel_id}'

    @property
    def days_since_published(self) -> int:
        datetime_published = datetime.strptime(self.published_at,
                                               '%Y-%m-%dT%H:%M:%SZ')
        delta = datetime.today() - datetime_published
        return delta.days

    # These properties need to make additional API calls to retrieve
    # this data.

    @cached_property
    def view_count(self) -> int:
        stats = get_youtube_client().videos().list(
            id=self.video_id, part='statistics').execute()
        return int(stats['items'][0]['statistics'].get('viewCount', 1))

    @cached_property
    def num_subs(self) -> int:
        subs_search = get_youtube_client().channels().list(
            id=self.channel_id, part='statistics').execute()
        channel_stats = subs_search['items'][0]['statistics']
        # You can hide your subscriber count for a channel, in which case
        # we arbitrarily pick a low number of DEFAULT_SUBSCRIBERS.
        if channel_stats['hiddenSubscriberCount']:
            return DEFAULT_SUBSCRIBERS
        return int(channel_stats['subscriberCount'])


def get_youtube_api_key() -> str:
    client = boto3.client('ssm')
    try:
        response = client.get_parameter(Name=SSM_PARAM_NAME, WithDecryption=True)
        return response['Parameter']['Value']
    except client.exceptions.ParameterNotFound:
        raise RuntimeError("Your Youtube API key is not configured.  "
                           "Please run the ./configure-api-key command.")


def get_youtube_client():
    global CLIENT
    if CLIENT is None:
        api_key = get_youtube_api_key()
        CLIENT = build('youtube', 'v3', developerKey=api_key)
    return CLIENT


def hydrate(results: Dict[str, Any]) -> List[VideoResult]:
    search_results = []
    for item in results['items']:
        snippet = item['snippet']
        obj = VideoResult(
            title=snippet['title'],
            description=snippet['description'],
            video_id=item['id']['videoId'],
            channel_id=snippet['channelId'],
            published_at=snippet['publishedAt']
        )
        search_results.append(obj)
    return search_results


def score_result(video: VideoResult) -> float:
    if video.num_subs == 0:
        views_to_subs = 0.0
    else:
        views_to_subs = video.view_count / float(video.num_subs)
    capped_ratio = min(views_to_subs, 5)
    if video.days_since_published == 0:
        days_since_published = 1
    else:
        days_since_published = video.days_since_published

    return (video.view_count * capped_ratio) / days_since_published


def search_youtube(keyword: str, order: str = 'viewCount',
                   max_results: int = 50,
                   within_days: Optional[int] = None) -> List[VideoResult]:
    kwargs = {
        'q': keyword,
        'part': 'snippet',
        'type': 'video',
        'order': order,
        'maxResults': max_results
    }
    if within_days is not None:
        search_start_date = datetime.today() - timedelta(within_days)
        published_after = datetime(
            year=search_start_date.year, month=search_start_date.month,
            day=search_start_date.day).strftime('%Y-%m-%dT%H:%M:%SZ')
        kwargs['publishedAfter'] = published_after
    results = get_youtube_client().search().list(**kwargs).execute()
    return hydrate(results)


def recommend_youtube_videos(
        search_term: str, num_results: int = 50,
        within_days: Optional[int] = None) -> List[VideoResult]:
    results = search_youtube(search_term, within_days=within_days)
    results.sort(key=score_result, reverse=True)
    return results[:num_results]


def send_email(subject: str, message: str,
               addresses: List[str], sender: str) -> None:
    client = boto3.client('ses')
    destination = {'ToAddresses': addresses}
    client.send_email(
        Destination=destination,
        Message={
            'Body': {
                'Html': {
                    'Charset': 'UTF-8',
                    'Data': message,
                }
            },
            'Subject': {
                'Charset': 'UTF-8',
                'Data': subject,
            }
        },
        Source=sender,
    )


def format_to_email_body(
        recommended_videos: Dict[str, List[VideoResult]]) -> str:
    all_lines = []
    for keyword, videos in recommended_videos.items():
        text = [f'<h3>Videos for <strong>{keyword}</strong></h3>', '<ul>']
        for video in videos:
            line = (
                f'<li><a href="{video.video_url}">{video.title}</a> - '
                f"{video.view_count} views, {video.num_subs} subscribers</li>"
            )
            text.append(line)
        text.append('</ul><br />')
        all_lines.append('\n'.join(text))
    return '\n'.join(all_lines)


# This is a lambda function that you can run on demand.
# It lets you query for recommended video by invoking the
# function directly and providing a ``keyword`` param in your
# event object: ``{"keyword": "my search term"}``.
@app.lambda_function()
def on_demand_search(event, context):
    search_term = event.get('keyword', '')
    if search_term:
        results = recommend_youtube_videos(search_term)
        return [
            {'title': r.title,
             'video_url': r.video_url,
             'view_count': r.view_count,
             'score': score_result(r)} for r in results
        ]
    return []


@app.schedule(Rate(7, unit=Rate.DAYS))
def weekly_report(event):
    print(
        f"Generating weekly report for search terms: {','.join(SEARCH_TERMS)}")
    all_recommended = {}
    for term in SEARCH_TERMS:
        if not term:
            continue
        all_recommended[term] = recommend_youtube_videos(term, within_days=7,
                                                         num_results=5)
    body = format_to_email_body(all_recommended)
    print(body)
    if body:
        send_email('Your weekly youtube recommendations',
                message=body, addresses=[REPORT_EMAIL_ADDRESS],
                sender=REPORT_EMAIL_ADDRESS)
