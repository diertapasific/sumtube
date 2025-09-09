import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from transformers import pipeline
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_JUSTIFY
import io
import re
import yt_dlp

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

    def retrieve_video_title(url):
        try:
            ydl_opts = {"quiet": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                video_title = info.get("title", "Title not found")
        except Exception as e:
            video_title = "Youtube Video "
        
        return video_title

    # --- Step 1: Fetch transcript ---
    try:
        with st.spinner("⏳ Fetching transcript..."):
            transcript = YouTubeTranscriptApi().fetch(video_id=video_id, languages=['en', 'id'])
            full_text = " ".join([snippet.text for snippet in transcript])
        st.success("✅ Transcript fetched!")
    except Exception as e:
        st.error(f"❌ Transcript fetch failed: {str(e)}")
        st.stop()

    # --- Step 2: Init summarizer ---
    try:
        summarizer = pipeline("summarization", model="facebook/bart-large-cnn")
    except Exception as e:
        st.error(f"❌ Summarizer init failed: {str(e)}")
        st.stop()

    # --- Step 3: Chunking transcript ---
    try:
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
    except Exception as e:
        st.error(f"❌ Chunking failed: {str(e)}")
        st.stop()

    # --- Step 4: Summarize chunks ---
    try:
        summaries = []
        for i, chunk in enumerate(chunks, 1):
            with st.spinner(f"✨ Summarizing chunk {i}/{len(chunks)}..."):
                if len(chunk.split()) < 25:  # too short, skip summarizer
                    summaries.append(chunk.strip())
                    continue

                try:
                    out = summarizer(
                        chunk,
                        max_new_tokens=100,
                        min_length=30,
                        do_sample=False
                    )
                    summaries.append(out[0]['summary_text'])
                except Exception:
                    st.warning(f"⚠️ Chunk {i} could not be summarized, keeping raw text.")
                    summaries.append(chunk.strip())

        # --- Step 4.2: Multi-pass summarization for final summary ---
        def compress_texts(text_list, max_new_tokens=250, min_length=80):
            """Summarize a list of texts into one shorter text."""
            combined = " ".join(text_list)
            out = summarizer(
                combined,
                max_new_tokens=max_new_tokens,
                min_length=min_length,
                do_sample=False
            )
            return out[0]['summary_text']

        with st.spinner("📝 Creating refined final summary..."):
            if len(summaries) > 10:  # only multi-pass if LOTS of chunks
                # Step 1: Break into groups of 5 summaries (less compression)
                grouped = [summaries[i:i+5] for i in range(0, len(summaries), 5 )]
                meta_summaries = [compress_texts(group, 200, 60) for group in grouped]

                # Step 2: Final summarization with bigger allowance
                final_summary = compress_texts(meta_summaries, 500, 200)
            else:
                # Direct summarization with more room
                final_summary = compress_texts(summaries, 500, 200)

    except Exception as e:
        st.error(f"❌ Summarization failed: {str(e)}")
        st.stop()

    # --- Step 5: PDF Generator ---
    try:
        def create_pdf(summary_text, bullet_points):
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=letter,
                rightMargin=50,
                leftMargin=50,
                topMargin=50,
                bottomMargin=50
            )

            styles = getSampleStyleSheet()
            
            # Custom styles
            title_style = ParagraphStyle(
                'title',
                parent=styles['Heading1'],
                fontSize=16,
                alignment=TA_JUSTIFY,
                spaceAfter=20
            )
            header_style = ParagraphStyle(
                'header',
                parent=styles['Heading2'],
                fontSize=13,
                alignment=TA_LEFT,
                spaceBefore=12,
                spaceAfter=6
            )
            text_style = ParagraphStyle(
                'body',
                parent=styles['Normal'],
                fontSize=11,
                alignment=TA_JUSTIFY,
                leading=15
            )

            elements = []
            
            video_title = retrieve_video_title(url)
            # Final Summary
            elements.append(Paragraph(f"“{video_title}” Summary", title_style))
            elements.append(Paragraph(summary_text, text_style))
            elements.append(Spacer(1, 12))

            # Bullet Points
            elements.append(Paragraph("Bullet Points:", header_style))
            bullet_items = [
                ListItem(Paragraph(bp, text_style), leftIndent=20) for bp in bullet_points
            ]
            elements.append(ListFlowable(bullet_items, bulletType='1', start='1'))

            # Build PDF
            doc.build(elements)
            buffer.seek(0)
            return buffer

        pdf_buffer = create_pdf(final_summary, summaries)
    except Exception as e:
        st.error(f"❌ PDF generation failed: {str(e)}")
        st.stop()

    # --- Step 6: UI Tabs ---
    try:
        tab_summary, tab_transcript = st.tabs(["📝 Summary", "📜 Transcript"])

        with tab_summary:
            st.subheader("📌 Final Summary")
            st.write(final_summary)

            st.markdown("### 🔹 Summary in Bullet Points")
            for i, s in enumerate(summaries, 1):
                st.markdown(f"- **Part {i}:** {s}")

            video_title = retrieve_video_title(url)

            # PDF download button
            st.download_button(
                label="⬇️ Download Summary as PDF",
                data=pdf_buffer,
                file_name=f"{video_title}_summary.pdf",
                mime="application/pdf"
            )

        with tab_transcript:
            st.subheader("📜 Full Transcript")
            st.write(full_text)
    except Exception as e:
        st.error(f"❌ UI rendering failed: {str(e)}")