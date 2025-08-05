"""
Tests for Vertex AI Worker Service
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.services.vertex_ai_worker import VertexAIWorkerService, VertexAIWorkerError
from src.models.base import JobStatus, JobType, OutputFormat


@pytest.fixture
def mock_settings():
    """Mock settings."""
    settings = Mock()
    settings.GOOGLE_CLOUD_PROJECT = "test-project"
    settings.CLOUD_TASKS_LOCATION = "us-central1"
    settings.CLOUD_TASKS_QUEUE = "test-queue"
    return settings


@pytest.fixture
def mock_job_repository():
    """Mock job repository."""
    repo = Mock()
    repo.update_status = AsyncMock()
    repo.update_started_at = AsyncMock()
    repo.update_completed_at = AsyncMock()
    repo.update_progress = AsyncMock()
    repo.update_error_message = AsyncMock()
    repo.update_output_files = AsyncMock()
    return repo


@pytest.fixture
def mock_storage_manager():
    """Mock storage manager."""
    manager = Mock()
    manager.initialize = AsyncMock()
    manager.get_bucket_names = Mock(return_value={
        'output': 'test-output-bucket'
    })
    manager.storage.upload_from_bytes = AsyncMock(return_value="https://test.com/file.glb")
    return manager


@pytest.fixture
def mock_trellis_service():
    """Mock TRELLIS service."""
    service = Mock()
    service.initialize = AsyncMock()
    service.process_image_to_3d = AsyncMock(return_value="mock_3d_model")
    service.process_text_to_3d = AsyncMock(return_value="mock_3d_model")
    return service


@pytest.fixture
def mock_model_converter():
    """Mock model converter."""
    converter = Mock()
    converter.convert_model = AsyncMock(return_value=[
        (OutputFormat.GLB, "/tmp/test.glb")
    ])
    return converter


@pytest.fixture
def vertex_ai_worker(
    mock_settings, 
    mock_job_repository, 
    mock_storage_manager,
    mock_trellis_service,
    mock_model_converter
):
    """Create Vertex AI worker with mocked dependencies."""
    with patch('src.services.vertex_ai_worker.get_settings', return_value=mock_settings), \
         patch('src.services.vertex_ai_worker.get_job_repository', return_value=mock_job_repository), \
         patch('src.services.vertex_ai_worker.get_storage_manager', return_value=mock_storage_manager), \
         patch('src.services.vertex_ai_worker.get_trellis_service', return_value=mock_trellis_service), \
         patch('src.services.vertex_ai_worker.get_model_converter_service', return_value=mock_model_converter), \
         patch('src.services.vertex_ai_worker.tasks_v2.CloudTasksClient'):
        
        worker = VertexAIWorkerService()
        return worker


class TestVertexAIWorkerService:
    """Test cases for Vertex AI Worker Service."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, vertex_ai_worker, mock_storage_manager, mock_trellis_service):
        """Test worker initialization."""
        # Mock Cloud Tasks client
        vertex_ai_worker.tasks_client.get_queue = Mock(return_value=Mock(name="test-queue"))
        
        await vertex_ai_worker._initialize_worker()
        
        # Verify initialization calls
        mock_storage_manager.initialize.assert_called_once()
        mock_trellis_service.initialize.assert_called_once()
        vertex_ai_worker.tasks_client.get_queue.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_image_to_3d_job(
        self, 
        vertex_ai_worker, 
        mock_job_repository,
        mock_trellis_service
    ):
        """Test processing image-to-3D job."""
        job_id = "test-job-123"
        input_data = {
            'image_url': 'https://test.com/image.jpg',
            'quality': 'high'
        }
        
        result = await vertex_ai_worker._process_image_to_3d(job_id, input_data)
        
        # Verify TRELLIS service called correctly
        mock_trellis_service.process_image_to_3d.assert_called_once_with(
            image_url='https://test.com/image.jpg',
            quality='high',
            progress_callback=pytest.any
        )
        
        # Verify progress updates
        assert mock_job_repository.update_progress.call_count >= 2
        
        assert result == "mock_3d_model"
    
    @pytest.mark.asyncio
    async def test_process_text_to_3d_job(
        self, 
        vertex_ai_worker, 
        mock_job_repository,
        mock_trellis_service
    ):
        """Test processing text-to-3D job."""
        job_id = "test-job-456"
        input_data = {
            'prompt': 'A red car',
            'negative_prompt': 'blurry',
            'quality': 'balanced'
        }
        
        result = await vertex_ai_worker._process_text_to_3d(job_id, input_data)
        
        # Verify TRELLIS service called correctly
        mock_trellis_service.process_text_to_3d.assert_called_once_with(
            prompt='A red car',
            negative_prompt='blurry',
            quality='balanced',
            progress_callback=pytest.any
        )
        
        # Verify progress updates
        assert mock_job_repository.update_progress.call_count >= 2
        
        assert result == "mock_3d_model"
    
    @pytest.mark.asyncio
    async def test_process_results(
        self, 
        vertex_ai_worker, 
        mock_job_repository,
        mock_storage_manager,
        mock_model_converter
    ):
        """Test processing and uploading results."""
        job_id = "test-job-789"
        user_id = "test-user"
        trellis_result = "mock_3d_model"
        input_data = {
            'output_formats': ['glb', 'obj'],
            'quality_settings': {'compression': 'high'}
        }
        
        # Mock file reading
        with patch('builtins.open', mock_open_binary(b'mock_file_data')):
            with patch('pathlib.Path.unlink'):
                output_files = await vertex_ai_worker._process_results(
                    job_id, user_id, trellis_result, input_data
                )
        
        # Verify model conversion
        mock_model_converter.convert_model.assert_called_once_with(
            input_data=trellis_result,
            target_formats=[OutputFormat.GLB, OutputFormat.OBJ],
            job_id=job_id,
            quality_settings={'compression': 'high'}
        )
        
        # Verify file upload
        mock_storage_manager.storage.upload_from_bytes.assert_called()
        
        # Verify progress update
        mock_job_repository.update_progress.assert_called_with(job_id, 0.9)
        
        # Verify output structure
        assert len(output_files) == 1  # Mocked converter returns 1 file
        assert output_files[0]['format'] == 'glb'
        assert output_files[0]['url'] == "https://test.com/file.glb"
        assert output_files[0]['size_bytes'] == 14  # len(b'mock_file_data')
    
    @pytest.mark.asyncio
    async def test_process_job_complete_flow(
        self, 
        vertex_ai_worker, 
        mock_job_repository,
        mock_storage_manager,
        mock_trellis_service,
        mock_model_converter
    ):
        """Test complete job processing flow."""
        payload = {
            'job_id': 'test-job-complete',
            'user_id': 'test-user',
            'job_type': JobType.TEXT_TO_3D.value,
            'input_data': {
                'prompt': 'A blue sphere',
                'output_formats': ['glb']
            }
        }
        
        # Mock file operations
        with patch('builtins.open', mock_open_binary(b'mock_glb_data')):
            with patch('pathlib.Path.unlink'):
                await vertex_ai_worker._process_job(payload)
        
        # Verify job status updates
        mock_job_repository.update_status.assert_any_call('test-job-complete', JobStatus.PROCESSING)
        mock_job_repository.update_status.assert_any_call('test-job-complete', JobStatus.COMPLETED)
        mock_job_repository.update_started_at.assert_called_once()
        mock_job_repository.update_completed_at.assert_called_once()
        mock_job_repository.update_output_files.assert_called_once()
        
        # Verify final progress
        mock_job_repository.update_progress.assert_any_call('test-job-complete', 1.0)
    
    @pytest.mark.asyncio
    async def test_job_failure_handling(
        self, 
        vertex_ai_worker, 
        mock_job_repository,
        mock_trellis_service
    ):
        """Test job failure handling."""
        job_id = "test-job-fail"
        error_message = "TRELLIS processing failed"
        
        # Make TRELLIS service fail
        mock_trellis_service.process_text_to_3d.side_effect = Exception(error_message)
        
        payload = {
            'job_id': job_id,
            'user_id': 'test-user',
            'job_type': JobType.TEXT_TO_3D.value,
            'input_data': {'prompt': 'A failing prompt'}
        }
        
        # Process job should raise exception
        with pytest.raises(Exception):
            await vertex_ai_worker._process_job(payload)
        
        # Verify failure handling
        await vertex_ai_worker._handle_job_failure(job_id, error_message)
        mock_job_repository.update_status.assert_any_call(job_id, JobStatus.FAILED)
        mock_job_repository.update_error_message.assert_called_with(job_id, error_message)
    
    @pytest.mark.asyncio
    async def test_missing_job_id_in_payload(self, vertex_ai_worker):
        """Test handling of payload without job_id."""
        payload = {
            'user_id': 'test-user',
            'job_type': JobType.TEXT_TO_3D.value,
            'input_data': {'prompt': 'Test prompt'}
        }
        
        with pytest.raises(KeyError):
            await vertex_ai_worker._process_job(payload)
    
    @pytest.mark.asyncio
    async def test_unknown_job_type(self, vertex_ai_worker, mock_job_repository):
        """Test handling of unknown job type."""
        payload = {
            'job_id': 'test-unknown-type',
            'user_id': 'test-user',
            'job_type': 'unknown_type',
            'input_data': {}
        }
        
        with pytest.raises(VertexAIWorkerError, match="Unknown job type"):
            await vertex_ai_worker._process_job(payload)


def mock_open_binary(data):
    """Helper to mock binary file opening."""
    from unittest.mock import mock_open
    return mock_open(read_data=data)


# Integration test fixtures and helpers

@pytest.fixture
def cloud_task_payload():
    """Sample Cloud Task payload."""
    return {
        'job_id': 'integration-test-job',
        'user_id': 'integration-user',
        'job_type': JobType.IMAGE_TO_3D.value,
        'input_data': {
            'image_url': 'https://example.com/test-image.jpg',
            'quality': 'balanced',
            'output_formats': ['glb', 'obj']
        },
        'created_at': datetime.utcnow().isoformat()
    }


@pytest.mark.integration
class TestVertexAIWorkerIntegration:
    """Integration tests for Vertex AI Worker (require actual GCP setup)."""
    
    @pytest.mark.asyncio
    async def test_worker_initialization_with_real_gcp(self):
        """Test worker initialization with real GCP services."""
        # This test requires actual GCP credentials and resources
        pytest.skip("Requires GCP setup")
    
    @pytest.mark.asyncio
    async def test_end_to_end_job_processing(self, cloud_task_payload):
        """Test end-to-end job processing."""
        # This test requires actual TRELLIS and GCP setup
        pytest.skip("Requires full infrastructure setup")