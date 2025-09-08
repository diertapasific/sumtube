import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from transformers import pipeline
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import io
import re

st.set_page_config(page_title="SumTube - YouTube Summarizer", page_icon="🎬", layout="centered")

st.title("🎬 SumTube: YouTube Video Summarizer")
st.write("Paste a YouTube link, and I'll fetch the transcript + generate a summary for you!")

# Input YouTube URL
url = st.text_input("📌 Paste a YouTube URL:")

if url:
    # Extract video ID
    match = re.search(r"v=([^&]+)", url)
    if match:
        video_id = match.group(1)
    else:
        st.error("❌ Invalid YouTube URL")
        st.stop()

    try:
        # Fetch transcript
        with st.spinner("⏳ Fetching transcript..."):
            transcript = YouTubeTranscriptApi().fetch(video_id=video_id, languages=['en'])
            full_text = " ".join([snippet.text for snippet in transcript])
        st.success("✅ Transcript fetched!")

        # Summarizer
        summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

        # Chunking
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

        # Summarize chunks
        summaries = []
        for i, chunk in enumerate(chunks, 1):
            with st.spinner(f"✨ Summarizing chunk {i}/{len(chunks)}..."):
                out = summarizer(chunk, max_length=120, min_length=40, do_sample=False)
                summaries.append(out[0]['summary_text'])

        final_summary = " ".join(summaries)

        # PDF generator
        def create_pdf(summary_text, bullet_points):
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=letter)
            width, height = letter

            # Title
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, height - 50, "YouTube Video Summary")

            # Final Summary
            c.setFont("Helvetica-Bold", 12)
            y = height - 100
            c.drawString(50, y, "Final Summary:")
            y -= 20

            c.setFont("Helvetica", 11)
            lines = simpleSplit(summary_text, "Helvetica", 11, width - 100)
            for line in lines:
                c.drawString(50, y, line)
                y -= 15

            # Bullet Points
            c.setFont("Helvetica-Bold", 12)
            y -= 10
            c.drawString(50, y, "Bullet Points:")
            y -= 20

            c.setFont("Helvetica", 11)
            for i, point in enumerate(bullet_points, 1):
                wrapped_lines = simpleSplit(point, "Helvetica", 11, width - 100)
                c.drawString(50, y, f"{i}. {wrapped_lines[0]}")
                y -= 15
                for line in wrapped_lines[1:]:
                    c.drawString(70, y, line)  # indent continuation lines
                    y -= 15
                y -= 5  # space between bullets

                if y < 50:
                    c.showPage()
                    y = height - 50
                    c.setFont("Helvetica", 11)

            c.showPage()
            c.save()
            buffer.seek(0)
            return buffer

        pdf_buffer = create_pdf(final_summary, summaries)

        # --- Tabs ---
        tab_summary, tab_transcript = st.tabs(["📝 Summary", "📜 Transcript"])

        with tab_summary:
            st.subheader("📌 Final Summary")
            st.write(final_summary)

            st.markdown("### 🔹 Summary in Bullet Points")
            for i, s in enumerate(summaries, 1):
                st.markdown(f"- **Part {i}:** {s}")

            # PDF download button
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
        st.error(f"❌ Could not fetch transcript: {str(e)}")
