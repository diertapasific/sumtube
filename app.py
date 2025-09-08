import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled
from transformers import pipeline
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import io
import re

st.set_page_config(page_title="SumTube - YouTube Summarizer", page_icon="🎬", layout="centered")

st.title("🎬 SumTube: YouTube Video Summarizer")
st.write("Paste a YouTube link, and I'll fetch the transcript + generate a summary for you!")

# --- PDF helper ---
def draw_text_block(c, text, x, y, width, line_height=15, font="Helvetica", font_size=11):
    """Draw wrapped text on PDF canvas, creating new pages if needed."""
    c.setFont(font, font_size)
    lines = simpleSplit(text, font, font_size, width)
    for line in lines:
        if y < 50:  # bottom margin
            c.showPage()
            y = 750  # reset y for new page
            c.setFont(font, font_size)
        c.drawString(x, y, line)
        y -= line_height
    return y

def create_pdf(final_summary, bullet_points):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "YouTube Video Summary")
    y -= 40

    # Final Summary
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Final Summary:")
    y -= 20
    y = draw_text_block(c, final_summary, 50, y, width - 100)

    # Bullet Points
    c.setFont("Helvetica-Bold", 12)
    y -= 10
    c.drawString(50, y, "Bullet Points:")
    y -= 20

    c.setFont("Helvetica", 11)
    for i, point in enumerate(bullet_points, 1):
        y = draw_text_block(c, f"{i}. {point}", 50, y, width - 100)
        y -= 5

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- Main ---
url = st.text_input("📌 Paste a YouTube URL:")

if url:
    match = re.search(r"v=([^&]+)", url)
    if not match:
        st.error("❌ Invalid YouTube URL")
        st.stop()
    video_id = match.group(1)

    try:
        # Fetch transcript safely
        with st.spinner("⏳ Fetching transcript..."):
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['en'])
            except TranscriptsDisabled:
                st.error("❌ Transcript is disabled for this video.")
                st.stop()
            except Exception as e:
                st.error(f"❌ Could not fetch transcript: {str(e)}")
                st.stop()

            if not transcript:
                st.error("❌ Transcript not available.")
                st.stop()

            full_text = " ".join([snippet['text'] for snippet in transcript if 'text' in snippet])
        st.success("✅ Transcript fetched!")

        # Summarizer
        summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

        # --- Chunking ---
        max_chunk = 800
        sentences = full_text.split(". ")
        chunks, current_chunk = [], ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_chunk:
                current_chunk += sentence + ". "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        if current_chunk:
            chunks.append(current_chunk.strip())

        # Summarize each chunk for bullet points
        summaries = []
        for i, chunk in enumerate(chunks, 1):
            with st.spinner(f"✨ Summarizing chunk {i}/{len(chunks)}..."):
                out = summarizer(chunk, max_length=120, min_length=40, do_sample=False)
                summaries.append(out[0]['summary_text'])

        # Second-level concise summary for long videos
        with st.spinner("✨ Generating final concise summary..."):
            joined_summaries = " ".join(summaries)
            # Avoid too long input for summarizer
            if len(joined_summaries) > 1000:
                final_summary_chunks = [joined_summaries[i:i+1000] for i in range(0, len(joined_summaries), 1000)]
                final_summary_list = [summarizer(chunk, max_length=150, min_length=50, do_sample=False)[0]['summary_text'] for chunk in final_summary_chunks]
                final_summary = " ".join(final_summary_list)
            else:
                final_summary = summarizer(joined_summaries, max_length=150, min_length=50, do_sample=False)[0]['summary_text']

        # Generate PDF
        pdf_buffer = create_pdf(final_summary, summaries)

        # --- Tabs ---
        tab_summary, tab_transcript = st.tabs(["📝 Summary", "📜 Transcript"])

        with tab_summary:
            st.subheader("📌 Final Summary")
            st.write(final_summary)

            st.markdown("### 🔹 Summary in Bullet Points")
            for i, s in enumerate(summaries, 1):
                st.markdown(f"- **Part {i}:** {s}")

            st.download_button(
                label="⬇️ Download Summary as PDF",
                data=pdf_buffer,
                file_name=f"{video_id}_summary.pdf",
                mime="application/pdf"
            )

        with tab_transcript:
            st.subheader("📜 Full Transcript")
            st.write(full_text)

    except Exception as e:
        st.error(f"❌ Could not process video: {str(e)}")
