"""
Script de ingest file quy-trinh-don-tiep-benh-nhan.md vao vector store.
"""

import asyncio
import os
import sys
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, 'strict')

# Thêm thư mục ai-service vào Python path để import được app module
project_root = Path(__file__).parent
ai_service_path = project_root / "ai-service"
sys.path.insert(0, str(ai_service_path))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

async def ingest_quy_trinh():
    """Ingest file quy-trinh-don-tiep-benh-nhan.md."""
    try:
        from app.config import get_settings
        from app.services.ingest_data.ingest.service import DefaultIngestService
        
        settings = get_settings()
        
        # Duong dan file can ingest
        file_path = project_root / "data" / "quy-trinh-don-tiep-benh-nhan.md"
        
        if not file_path.exists():
            print(f"ERROR: File khong ton tai: {file_path}")
            return False
        
        print(f"Bat dau ingest file: {file_path}")
        print(f"Kich thuoc file: {file_path.stat().st_size} bytes")
        
        # Khoi tao service
        service = DefaultIngestService(settings)
        
        # Chay ingest
        result = await service.ingest(
            data_source_api=str(file_path),
            data_type="document",
            metadata={
                "title": "Quy trinh don tiep benh nhan",
                "source": "quy-trinh-don-tiep-benh-nhan.md",
                "category": "hospital_procedure"
            }
        )
        
        print(f"\n{'='*60}")
        print("INGEST THANH CONG!")
        print(f"{'='*60}")
        print(f"Document ID: {result['document_id']}")
        print(f"So chunks da tao: {result['records_processed']}")
        print(f"Thoi gian xu ly: {result['latency_ms']:.2f} ms")
        print(f"{'='*60}")
        
        return True
        
    except Exception as e:
        print(f"\nERROR: Loi khi ingest file!")
        print(f"Loai loi: {type(e).__name__}")
        print(f"Chi tiet: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(ingest_quy_trinh())
    sys.exit(0 if success else 1)
