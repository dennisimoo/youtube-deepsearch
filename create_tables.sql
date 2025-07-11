-- Create tables for YouTube Deep Summary application

-- Table for storing YouTube video metadata
CREATE TABLE IF NOT EXISTS youtube_videos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_id VARCHAR(11) UNIQUE NOT NULL,
    title TEXT,
    uploader TEXT,
    duration INTEGER,
    thumbnail_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for storing video transcripts
CREATE TABLE IF NOT EXISTS transcripts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_id VARCHAR(11) NOT NULL REFERENCES youtube_videos(video_id) ON DELETE CASCADE,
    transcript_data JSONB NOT NULL, -- Raw transcript with timestamps
    formatted_transcript TEXT NOT NULL, -- Formatted readable transcript
    language_used VARCHAR(10),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for storing video chapters
CREATE TABLE IF NOT EXISTS video_chapters (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_id VARCHAR(11) NOT NULL REFERENCES youtube_videos(video_id) ON DELETE CASCADE,
    chapters_data JSONB, -- Array of chapter objects
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for storing AI summaries
CREATE TABLE IF NOT EXISTS summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_id VARCHAR(11) NOT NULL REFERENCES youtube_videos(video_id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    model_used VARCHAR(50) DEFAULT 'gpt-4.1',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Table for storing user memories (saved text snippets)
CREATE TABLE IF NOT EXISTS memories (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    video_id VARCHAR(11) NOT NULL REFERENCES youtube_videos(video_id) ON DELETE CASCADE,
    selected_text TEXT NOT NULL,
    context_text TEXT, -- Additional context around the selection
    source_type VARCHAR(20) NOT NULL DEFAULT 'transcript', -- 'transcript' or 'summary'
    timestamp_seconds INTEGER, -- For transcript memories, the timestamp
    note TEXT, -- User's optional note about this memory
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_youtube_videos_video_id ON youtube_videos(video_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_video_id ON transcripts(video_id);
CREATE INDEX IF NOT EXISTS idx_video_chapters_video_id ON video_chapters(video_id);
CREATE INDEX IF NOT EXISTS idx_summaries_video_id ON summaries(video_id);
CREATE INDEX IF NOT EXISTS idx_memories_video_id ON memories(video_id);
CREATE INDEX IF NOT EXISTS idx_youtube_videos_created_at ON youtube_videos(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transcripts_created_at ON transcripts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_summaries_created_at ON summaries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);

-- Enable Row Level Security (RLS) for better security
ALTER TABLE youtube_videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE transcripts ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_chapters ENABLE ROW LEVEL SECURITY;
ALTER TABLE summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;

-- Create policies to allow public access (adjust based on your security needs)
CREATE POLICY "Allow public access to youtube_videos" ON youtube_videos FOR ALL USING (true);
CREATE POLICY "Allow public access to transcripts" ON transcripts FOR ALL USING (true);
CREATE POLICY "Allow public access to video_chapters" ON video_chapters FOR ALL USING (true);
CREATE POLICY "Allow public access to summaries" ON summaries FOR ALL USING (true);
CREATE POLICY "Allow public access to memories" ON memories FOR ALL USING (true);