#!/usr/bin/env python3
"""
YouTube Transcript Web Viewer

A Flask web application that accepts YouTube video IDs and displays transcripts.
"""

import os
from flask import Flask, request, render_template, jsonify
from youtube_transcript_api import YouTubeTranscriptApi
import re
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    print("Warning: markdown library not available. Install with: pip install markdown")
from transcript_summarizer import TranscriptSummarizer, format_transcript_for_readability, extract_video_chapters, extract_video_info
from database_storage import database_storage
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Add custom markdown filter for templates
@app.template_filter('markdown')
def markdown_filter(text):
    """Convert markdown text to HTML"""
    if MARKDOWN_AVAILABLE:
        # Pre-process bullet points to proper markdown lists
        processed_text = text.replace('• ', '* ')
        return markdown.markdown(processed_text, extensions=['nl2br', 'tables'])
    else:
        # Fallback: convert bullet points to HTML list
        lines = text.split('\n')
        html_lines = []
        in_list = False
        
        for line in lines:
            line = line.strip()
            if line.startswith('• '):
                if not in_list:
                    html_lines.append('<ul>')
                    in_list = True
                html_lines.append(f'<li>{line[2:]}</li>')
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                if line:
                    html_lines.append(f'<p>{line}</p>')
                else:
                    html_lines.append('<br>')
        
        if in_list:
            html_lines.append('</ul>')
        
        return ''.join(html_lines)

# Initialize summarizer with error handling
try:
    summarizer = TranscriptSummarizer()
    print(f"Summarizer initialized. OpenAI configured: {summarizer.is_configured()}")
except Exception as e:
    print(f"Warning: Failed to initialize summarizer: {e}")
    summarizer = None

def extract_video_id(url_or_id):
    """Extract video ID from YouTube URL or return if already an ID"""
    # If it's already an 11-character ID, return it
    if len(url_or_id) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    
    # Extract from URL patterns
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/.*[?&]v=([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    
    return None

def get_transcript(video_id):
    """Download transcript for given video ID using proxy from environment with language fallback"""
    try:
        proxies = None
        proxy = os.getenv('YOUTUBE_PROXY')
        
        if proxy:
            proxies = {
                'http': f'http://{proxy}',
                'https': f'http://{proxy}'
            }
            print(f"Using proxy: {proxy}")
        else:
            print("No proxy configured")
        
        print(f"Fetching transcript for video ID: {video_id}")
        
        # First try to get English transcript directly
        try:
            transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'], proxies=proxies)
            print(f"Successfully fetched English transcript with {len(transcript_list)} entries")
            language_used = "en (English)"
        except Exception as e:
            print(f"English transcript not available: {str(e)}")
            
            # If English not available, get the first available transcript
            try:
                print("Attempting to find available transcripts...")
                transcript_list_data = YouTubeTranscriptApi.list_transcripts(video_id, proxies=proxies)
                
                # Get list of available language codes
                available_languages = []
                for transcript in transcript_list_data:
                    available_languages.append(transcript.language_code)
                    print(f"Available: {transcript.language} ({transcript.language_code})")
                
                if available_languages:
                    # Use the first available language code with the standard get_transcript method
                    first_lang = available_languages[0]
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=[first_lang], proxies=proxies)
                    
                    # Get language name for logging
                    first_transcript = next(iter(transcript_list_data))
                    language_used = f"{first_transcript.language} ({first_transcript.language_code})"
                    print(f"Successfully fetched {language_used} transcript with {len(transcript_list)} entries")
                else:
                    raise Exception("No transcripts found")
                    
            except Exception as fallback_error:
                print(f"Fallback transcript fetch failed: {str(fallback_error)}")
                raise Exception(f"No transcripts available for this video: {str(fallback_error)}")
        
        # Format the transcript
        formatted_transcript = []
        for entry in transcript_list:
            formatted_transcript.append({
                'time': entry['start'],
                'text': entry['text'],
                'formatted_time': f"{int(entry['start'] // 60):02d}:{int(entry['start'] % 60):02d}"
            })
        
        print(f"Transcript language used: {language_used}")
        return formatted_transcript
        
    except Exception as e:
        print(f"Error in get_transcript: {str(e)}")
        raise Exception(f"Error downloading transcript: {str(e)}")

@app.route('/')
def index():
    """Home page with instructions"""
    return render_template('index.html')

@app.route('/watch')
def watch():
    """Display transcript for YouTube video"""
    video_id_param = request.args.get('v')
    # Remove summarize parameter since we're using AJAX now
    # summarize = request.args.get('summarize', 'false').lower() == 'true'
    
    if not video_id_param:
        return render_template('error.html', 
                             error_message="No video ID provided. Please use /watch?v=VIDEO_ID"), 400
    
    video_id = extract_video_id(video_id_param)
    
    if not video_id:
        return render_template('error.html', 
                             error_message="Invalid video ID format"), 400
    
    try:
        # Check database first
        cached_data = database_storage.get(video_id)
        
        if cached_data:
            print(f"Using cached data for video: {video_id}")
            transcript = cached_data['transcript']
            video_info = cached_data['video_info']
            formatted_transcript_text = cached_data['formatted_transcript']
            
            video_title = video_info.get('title')
            chapters = video_info.get('chapters')
            video_duration = video_info.get('duration')
            video_uploader = video_info.get('uploader')
        else:
            print(f"Database MISS for video: {video_id}, downloading fresh data")
            transcript = get_transcript(video_id)
            
            # Extract video info (title, chapters, etc.)
            print(f"Extracting video info for: {video_id}")
            try:
                video_info = extract_video_info(video_id)
                video_title = video_info.get('title')
                chapters = video_info.get('chapters')
                video_duration = video_info.get('duration')
                video_uploader = video_info.get('uploader')
                
                print(f"Video title: {video_title}")
                print(f"Chapters extracted: {chapters}")
                if chapters:
                    print(f"Found {len(chapters)} chapters")
                else:
                    print("No chapters found or chapter extraction failed")
            except Exception as e:
                print(f"Video info extraction error: {e}")
                video_info = {
                    'title': None,
                    'chapters': None,
                    'duration': None,
                    'uploader': None
                }
                video_title = None
                chapters = None
                video_duration = None
                video_uploader = None
            
            # Format transcript for improved readability
            formatted_transcript_text = format_transcript_for_readability(transcript, chapters)
            
            # Store the data in database for future use
            database_storage.set(video_id, transcript, video_info, formatted_transcript_text)
        
        proxy_used = os.getenv('YOUTUBE_PROXY', 'None')
        
        # Check for existing summary
        existing_summary = database_storage.get_summary(video_id)
        if existing_summary:
            # Convert markdown to HTML if markdown library is available
            if MARKDOWN_AVAILABLE:
                # Pre-process bullet points to proper markdown lists
                processed_summary = existing_summary.replace('• ', '* ')
                summary = markdown.markdown(processed_summary, extensions=['nl2br', 'tables'])
                print(f"Converted existing summary for {video_id}: markdown -> HTML conversion applied")
            else:
                summary = existing_summary.replace('\n', '<br>').replace('• ', '• ')
                print(f"Fallback for {video_id}: markdown library not available")
        else:
            summary = None
        summary_error = None
        
        # Generate thumbnail URL
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        
        return render_template('transcript.html', 
                             video_id=video_id,
                             video_title=video_title,
                             video_duration=video_duration,
                             video_uploader=video_uploader,
                             transcript=transcript,
                             formatted_transcript=formatted_transcript_text,
                             chapters=chapters,
                             thumbnail_url=thumbnail_url,
                             proxy_used=proxy_used,
                             summary=summary,
                             summary_error=summary_error,
                             summarize_enabled=summarizer and summarizer.is_configured())
        
    except Exception as e:
        return render_template('error.html', 
                             error_message=str(e)), 500

@app.route('/api/transcript/<video_id>')
def api_transcript(video_id):
    """API endpoint to get transcript as JSON"""
    try:
        # Check database first for API endpoint too
        cached_data = database_storage.get(video_id)
        
        if cached_data:
            print(f"API: Using cached data for video: {video_id}")
            transcript = cached_data['transcript']
            video_info = cached_data['video_info']
            formatted_transcript = cached_data['formatted_transcript']
            chapters = video_info.get('chapters')
        else:
            print(f"API: Database MISS for video: {video_id}, downloading fresh data")
            transcript = get_transcript(video_id)
            video_info = extract_video_info(video_id)
            chapters = video_info.get('chapters')
            formatted_transcript = format_transcript_for_readability(transcript, chapters)
            
            # Store the data in database
            database_storage.set(video_id, transcript, video_info, formatted_transcript)
        
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'video_title': video_info.get('title'),
            'video_duration': video_info.get('duration'),
            'video_uploader': video_info.get('uploader'),
            'transcript': transcript,
            'formatted_transcript': formatted_transcript,
            'chapters': chapters,
            'thumbnail_url': thumbnail_url,
            'proxy_used': os.getenv('YOUTUBE_PROXY', None)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/summary/<video_id>')
def api_summary(video_id):
    """API endpoint to get transcript summary as JSON (legacy - downloads transcript)"""
    try:
        if not summarizer or not summarizer.is_configured():
            return jsonify({
                'success': False,
                'error': 'OpenAI API key not configured'
            }), 400
        
        transcript = get_transcript(video_id)
        summary = summarizer.summarize_transcript(transcript)
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'summary': summary,
            'proxy_used': os.getenv('YOUTUBE_PROXY', None)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/summary', methods=['POST'])
def api_summary_with_data():
    """API endpoint to generate summary from provided transcript data"""
    try:
        if not summarizer or not summarizer.is_configured():
            return jsonify({
                'success': False,
                'error': 'OpenAI API key not configured'
            }), 400
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        video_id = data.get('video_id')
        formatted_transcript = data.get('formatted_transcript')
        
        if not video_id or not formatted_transcript:
            return jsonify({
                'success': False,
                'error': 'video_id and formatted_transcript are required'
            }), 400
        
        # First check if summary already exists in database
        existing_summary = database_storage.get_summary(video_id)
        if existing_summary:
            print(f"Using existing summary for video {video_id}")
            return jsonify({
                'success': True,
                'video_id': video_id,
                'summary': existing_summary,
                'from_cache': True
            })
        
        # Get video info and chapters from database to include in summary
        cached_data = database_storage.get(video_id)
        chapters = None
        video_info = None
        if cached_data and cached_data.get('video_info'):
            video_info = cached_data['video_info']
            chapters = video_info.get('chapters')
        
        # Generate new summary using provided formatted transcript text
        print(f"Generating new summary for video {video_id}")
        summary = summarizer.summarize_with_openai(formatted_transcript, chapters=chapters, video_id=video_id, video_info=video_info)
        
        # Save the summary to database
        try:
            database_storage.save_summary(video_id, summary)
            print(f"Summary saved to database for video {video_id}")
        except Exception as e:
            print(f"Warning: Failed to save summary to database: {e}")
        
        return jsonify({
            'success': True,
            'video_id': video_id,
            'summary': summary,
            'from_cache': False
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cache/info')
def api_cache_info():
    """API endpoint to get database statistics"""
    try:
        cache_info = database_storage.get_cache_info()
        return jsonify({
            'success': True,
            'cache_info': cache_info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cache/cleanup', methods=['POST'])
def api_cache_cleanup():
    """API endpoint to clean up expired cache files (no-op for database)"""
    try:
        database_storage.clear_expired()
        cache_info = database_storage.get_cache_info()
        return jsonify({
            'success': True,
            'message': 'Database cleanup completed (no action needed)',
            'cache_info': cache_info
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/storage')
def storage_page():
    """Display all saved videos"""
    try:
        cached_videos = database_storage.get_all_cached_videos()
        cache_stats = database_storage.get_cache_info()
        
        return render_template('storage.html', 
                             cached_videos=cached_videos,
                             cache_stats=cache_stats)
    except Exception as e:
        return render_template('error.html', 
                             error_message=f"Error loading storage page: {str(e)}"), 500

@app.route('/api/delete/<video_id>', methods=['DELETE'])
def api_delete_video(video_id):
    """API endpoint to delete a video from storage"""
    try:
        success = database_storage.delete(video_id)
        if success:
            return jsonify({'success': True, 'message': f'Video {video_id} deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Failed to delete video'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/channels')
def channels_page():
    """Display all channels with video counts"""
    try:
        channels = database_storage.get_all_channels()
        return render_template('channels.html', channels=channels)
    except Exception as e:
        return render_template('error.html', 
                             error_message=f"Error loading channels: {str(e)}"), 500

@app.route('/channel/<channel_name>/videos')
def channel_videos(channel_name):
    """Display all videos from a specific channel"""
    try:
        # Get all videos for the channel
        channel_videos_list = database_storage.get_videos_by_channel(channel_name)
        
        if not channel_videos_list:
            return render_template('error.html', 
                                 error_message=f"No videos found for channel: {channel_name}"), 404
        
        # Check which videos have summaries
        for video in channel_videos_list:
            video['has_summary'] = database_storage.get_summary(video['video_id']) is not None
            video['thumbnail_url'] = f"https://img.youtube.com/vi/{video['video_id']}/maxresdefault.jpg"
        
        return render_template('channel_videos.html', 
                             channel_name=channel_name,
                             videos=channel_videos_list,
                             total_videos=len(channel_videos_list))
        
    except Exception as e:
        return render_template('error.html', 
                             error_message=f"Error loading channel videos: {str(e)}"), 500

@app.route('/channel/<channel_name>/summaries')
def channel_summaries(channel_name):
    """Display AI summaries for all videos from a specific channel"""
    try:
        # Get all videos for the channel
        channel_videos = database_storage.get_videos_by_channel(channel_name)
        
        if not channel_videos:
            return render_template('error.html', 
                                 error_message=f"No videos found for channel: {channel_name}"), 404
        
        # Get summaries for each video
        summaries = []
        for video in channel_videos:
            video_id = video['video_id']
            summary = database_storage.get_summary(video_id)
            
            if summary:
                # Convert markdown to HTML if markdown library is available
                if MARKDOWN_AVAILABLE:
                    # Pre-process bullet points to proper markdown lists
                    processed_summary = summary.replace('• ', '* ')
                    summary_html = markdown.markdown(processed_summary, extensions=['nl2br', 'tables'])
                    print(f"Converted summary for {video_id}: markdown -> HTML conversion applied")
                else:
                    summary_html = summary.replace('\n', '<br>').replace('• ', '• ')
                    print(f"Fallback for {video_id}: markdown library not available")
                
                summaries.append({
                    'video_id': video_id,
                    'title': video['title'],
                    'uploader': video['uploader'],
                    'duration': video['duration'],
                    'thumbnail_url': f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                    'summary': summary_html,
                    'created_at': video['created_at']
                })
        
        return render_template('channel_summaries.html', 
                             channel_name=channel_name,
                             summaries=summaries,
                             total_videos=len(channel_videos),
                             summarized_videos=len(summaries))
        
    except Exception as e:
        return render_template('error.html', 
                             error_message=f"Error loading channel summaries: {str(e)}"), 500

@app.route('/memories')
def memories_page():
    """Display user's saved memories grouped by channel"""
    try:
        # Always group by channel for the new simplified design
        memories_data = database_storage.get_memories(group_by_channel=True)
        
        # Get memory statistics
        memory_stats = database_storage.get_memory_stats()
        
        return render_template('memories.html', 
                             memories=memories_data,
                             memory_stats=memory_stats)
    except Exception as e:
        return render_template('error.html', 
                             error_message=f"Error loading memories: {str(e)}"), 500

@app.route('/memories/channel/<path:channel_name>')
def channel_memories(channel_name):
    """Display individual memories for a specific channel grouped by video"""
    try:
        # Get all memories for this channel
        all_memories = database_storage.get_memories()
        channel_memories_list = [m for m in all_memories if m.get('video_uploader') == channel_name]
        
        if not channel_memories_list:
            return render_template('error.html', 
                                 error_message=f"No memories found for channel: {channel_name}"), 404
        
        # Group memories by video
        videos_with_memories = {}
        for memory in channel_memories_list:
            video_id = memory['video_id']
            if video_id not in videos_with_memories:
                videos_with_memories[video_id] = {
                    'video_info': {
                        'video_id': video_id,
                        'title': memory['video_title'],
                        'uploader': memory['video_uploader'],
                        'thumbnail_url': memory['thumbnail_url']
                    },
                    'memories': []
                }
            videos_with_memories[video_id]['memories'].append(memory)
        
        # Convert to list and sort by video title
        grouped_videos = list(videos_with_memories.values())
        grouped_videos.sort(key=lambda x: x['video_info']['title'] or '')
        
        # Get stats
        unique_videos = len(grouped_videos)
        total_memories = len(channel_memories_list)
        
        return render_template('channel_memories.html', 
                             channel_name=channel_name,
                             grouped_videos=grouped_videos,
                             total_memories=total_memories,
                             unique_videos=unique_videos)
        
    except Exception as e:
        return render_template('error.html', 
                             error_message=f"Error loading channel memories: {str(e)}"), 500

@app.route('/api/memories', methods=['POST'])
def api_save_memory():
    """API endpoint to save a new memory"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No JSON data provided'
            }), 400
        
        video_id = data.get('video_id')
        selected_text = data.get('selected_text')
        source_type = data.get('source_type', 'transcript')
        context_text = data.get('context_text')
        timestamp_seconds = data.get('timestamp_seconds')
        note = data.get('note')
        
        if not video_id or not selected_text:
            return jsonify({
                'success': False,
                'error': 'video_id and selected_text are required'
            }), 400
        
        # Save memory to database
        success = database_storage.save_memory(
            video_id=video_id,
            selected_text=selected_text,
            source_type=source_type,
            context_text=context_text,
            timestamp_seconds=timestamp_seconds,
            note=note
        )
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Memory saved successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Memory already exists or failed to save'
            }), 400
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/memories/<memory_id>', methods=['DELETE'])
def api_delete_memory(memory_id):
    """API endpoint to delete a memory"""
    try:
        success = database_storage.delete_memory(memory_id)
        if success:
            return jsonify({
                'success': True,
                'message': f'Memory {memory_id} deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to delete memory'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/memories/<video_id>')
def api_get_video_memories(video_id):
    """API endpoint to get memories for a specific video"""
    try:
        memories = database_storage.get_memories(video_id=video_id)
        return jsonify({
            'success': True,
            'memories': memories
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/favicon.ico')
def favicon():
    """Serve favicon from static directory"""
    return app.send_static_file('favicon.ico')

if __name__ == '__main__':
    # Initialize database storage on startup
    database_storage.clear_expired()
    
    # Get configuration from environment variables
    proxy = os.getenv('YOUTUBE_PROXY')
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 33079))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    if proxy:
        print(f"Using proxy: {proxy}")
    else:
        print("No proxy configured")
    
    print(f"OpenAI API configured: {bool(os.getenv('OPENAI_API_KEY'))}")
    
    # Show database info
    cache_info = database_storage.get_cache_info()
    print(f"Database: {cache_info['videos_count']} videos, {cache_info['transcripts_count']} transcripts, {cache_info['summaries_count']} summaries")
    
    app.run(host=host, port=port, debug=debug)