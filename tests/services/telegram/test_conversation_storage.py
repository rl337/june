"""
Tests for ConversationStorage class.
"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
import json

# Mock psycopg2 before importing conversation_storage
sys.modules['psycopg2'] = MagicMock()
sys.modules['psycopg2.extras'] = MagicMock()
sys.modules['psycopg2.extras'].RealDictCursor = MagicMock

from essence.services.telegram.conversation_storage import ConversationStorage, DEFAULT_LANGUAGE


class TestConversationStorage:
    """Test ConversationStorage methods."""
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_language_preference_existing(self, mock_get_conn):
        """Test getting language preference when it exists in metadata."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        
        # Mock result with language preference in metadata
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'metadata': {'language_preference': 'es'}
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        # Test
        result = ConversationStorage.get_language_preference("user123", "chat456")
        
        # Verify
        assert result == "es"
        mock_cursor.execute.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_language_preference_default(self, mock_get_conn):
        """Test getting language preference when not set (should default to 'en')."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock result with no language preference
        mock_cursor.fetchone.return_value = None
        
        # Test
        result = ConversationStorage.get_language_preference("user123", "chat456")
        
        # Verify - should default to "en"
        assert result == DEFAULT_LANGUAGE
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_language_preference_empty_metadata(self, mock_get_conn):
        """Test getting language preference when metadata is empty."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock result with empty metadata
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'metadata': {}
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        # Test
        result = ConversationStorage.get_language_preference("user123", "chat456")
        
        # Verify - should default to "en"
        assert result == DEFAULT_LANGUAGE
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_set_language_preference_existing_conversation(self, mock_get_conn):
        """Test setting language preference for existing conversation."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock existing conversation
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'metadata': {}
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        # Test
        result = ConversationStorage.set_language_preference("user123", "chat456", "fr")
        
        # Verify
        assert result is True
        # Should call UPDATE
        assert mock_cursor.execute.call_count == 2  # SELECT then UPDATE
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_set_language_preference_new_conversation(self, mock_get_conn):
        """Test setting language preference for new conversation."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock no existing conversation
        mock_cursor.fetchone.return_value = None
        
        # Test
        result = ConversationStorage.set_language_preference("user123", "chat456", "de")
        
        # Verify
        assert result is True
        # Should call SELECT first (to check if exists), then INSERT
        assert mock_cursor.execute.call_count == 2  # SELECT, then INSERT
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_set_language_preference_preserves_metadata(self, mock_get_conn):
        """Test that setting language preference preserves other metadata."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock existing conversation with other metadata
        existing_metadata = {
            'detected_language': 'es',
            'some_other_field': 'value'
        }
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'metadata': existing_metadata
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        # Test
        result = ConversationStorage.set_language_preference("user123", "chat456", "fr")
        
        # Verify
        assert result is True
        # Check that UPDATE was called with metadata that includes both old and new fields
        update_call = [call for call in mock_cursor.execute.call_args_list 
                      if 'UPDATE' in str(call)]
        assert len(update_call) > 0
        # The metadata should include both the new language_preference and existing fields
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_set_language_preference_lowercase(self, mock_get_conn):
        """Test that language code is normalized to lowercase."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock existing conversation
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'metadata': {}
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        # Test with uppercase language code
        result = ConversationStorage.set_language_preference("user123", "chat456", "ES")
        
        # Verify
        assert result is True
        # Should normalize to lowercase
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_language_preference_error_handling(self, mock_get_conn):
        """Test error handling in get_language_preference."""
        # Mock database connection to raise exception
        mock_get_conn.side_effect = Exception("Database error")
        
        # Test - should return default on error
        result = ConversationStorage.get_language_preference("user123", "chat456")
        
        # Verify - should return default
        assert result == DEFAULT_LANGUAGE
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_set_language_preference_error_handling(self, mock_get_conn):
        """Test error handling in set_language_preference."""
        # Mock database connection to raise exception
        mock_get_conn.side_effect = Exception("Database error")
        
        # Test - should return False on error
        result = ConversationStorage.set_language_preference("user123", "chat456", "es")
        
        # Verify - should return False
        assert result is False
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_conversation_analytics_with_messages(self, mock_get_conn):
        """Test getting conversation analytics with messages."""
        from datetime import datetime, timedelta
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock conversation exists
        mock_conv_result = MagicMock()
        mock_conv_result.__getitem__.side_effect = lambda key: {
            'id': 'conv-123'
        }[key]
        
        # Mock messages - RealDictCursor returns dict-like objects
        base_time = datetime.now()
        mock_messages = []
        for role, content, offset in [
            ('user', 'Hello', 0),
            ('assistant', 'Hi there', 5),
            ('user', 'How are you?', 10),
            ('assistant', 'I am fine', 15)
        ]:
            msg_time = base_time + timedelta(seconds=offset)
            # Create a proper closure for the lambda
            def make_getitem(r, c, t):
                return lambda self, key: {
                    'role': r,
                    'content': c,
                    'created_at': t
                }[key]
            msg = type('MockRow', (), {
                '__getitem__': make_getitem(role, content, msg_time)
            })()
            mock_messages.append(msg)
        
        # Setup fetchone for conversation, fetchall for messages
        mock_cursor.fetchone.side_effect = [mock_conv_result, None]
        mock_cursor.fetchall.return_value = mock_messages
        
        # Test
        result = ConversationStorage.get_conversation_analytics("user123", "chat456")
        
        # Verify
        assert result['conversation_id'] == 'conv-123'
        assert result['message_count'] == 4
        assert result['user_message_count'] == 2
        assert result['assistant_message_count'] == 2
        assert result['average_response_time_seconds'] > 0
        assert 'engagement_score' in result
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_conversation_analytics_no_conversation(self, mock_get_conn):
        """Test getting analytics for non-existent conversation."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock no conversation
        mock_cursor.fetchone.return_value = None
        
        # Test
        result = ConversationStorage.get_conversation_analytics("user123", "chat456")
        
        # Verify
        assert result['conversation_id'] is None
        assert result['message_count'] == 0
        assert result['average_response_time_seconds'] == 0.0
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_dashboard_analytics(self, mock_get_conn):
        """Test getting dashboard analytics."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock results for different queries
        mock_conv_result = MagicMock()
        mock_conv_result.__getitem__.side_effect = lambda key: {
            'total_conversations': 10
        }[key]
        
        mock_msg_result = MagicMock()
        mock_msg_result.__getitem__.side_effect = lambda key: {
            'total_messages': 100,
            'user_messages': 50,
            'assistant_messages': 50
        }[key]
        
        mock_response_result = MagicMock()
        mock_response_result.__getitem__.side_effect = lambda key: {
            'avg_response_time': 2.5
        }[key]
        
        mock_users_result = MagicMock()
        mock_users_result.__getitem__.side_effect = lambda key: {
            'active_users': 5
        }[key]
        
        mock_cursor.fetchone.side_effect = [
            mock_conv_result,
            mock_msg_result,
            mock_response_result,
            mock_users_result
        ]
        
        # Test
        result = ConversationStorage.get_dashboard_analytics()
        
        # Verify
        assert result['total_conversations'] == 10
        assert result['total_messages'] == 100
        assert result['user_messages'] == 50
        assert result['assistant_messages'] == 50
        assert result['average_response_time_seconds'] == 2.5
        assert result['active_users'] == 5
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_dashboard_analytics_with_date_filter(self, mock_get_conn):
        """Test getting dashboard analytics with date filters."""
        from datetime import datetime
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock results
        mock_results = []
        for _ in range(4):
            mock_result = MagicMock()
            mock_result.__getitem__.side_effect = lambda key, val=0: {
                'total_conversations': 5,
                'total_messages': 50,
                'user_messages': 25,
                'assistant_messages': 25,
                'avg_response_time': 2.0,
                'active_users': 3
            }[key]
            mock_results.append(mock_result)
        
        mock_cursor.fetchone.side_effect = mock_results
        
        # Test with date filters
        start_date = datetime(2025, 1, 1)
        end_date = datetime(2025, 1, 31)
        result = ConversationStorage.get_dashboard_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        # Verify
        assert 'start_date' in result
        assert 'end_date' in result
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_generate_analytics_report_json(self, mock_get_conn):
        """Test generating JSON analytics report."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock dashboard analytics results
        mock_results = []
        for _ in range(4):
            mock_result = MagicMock()
            mock_result.__getitem__.side_effect = lambda key: {
                'total_conversations': 10,
                'total_messages': 100,
                'user_messages': 50,
                'assistant_messages': 50,
                'avg_response_time': 2.5,
                'active_users': 5
            }[key]
            mock_results.append(mock_result)
        
        mock_cursor.fetchone.side_effect = mock_results
        
        # Test
        report = ConversationStorage.generate_analytics_report(format="json")
        
        # Verify
        assert isinstance(report, str)
        import json
        data = json.loads(report)
        assert 'total_conversations' in data
        assert 'total_messages' in data
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_generate_analytics_report_csv(self, mock_get_conn):
        """Test generating CSV analytics report."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock dashboard analytics results
        mock_results = []
        for _ in range(4):
            mock_result = MagicMock()
            mock_result.__getitem__.side_effect = lambda key: {
                'total_conversations': 10,
                'total_messages': 100,
                'user_messages': 50,
                'assistant_messages': 50,
                'avg_response_time': 2.5,
                'active_users': 5
            }[key]
            mock_results.append(mock_result)
        
        mock_cursor.fetchone.side_effect = mock_results
        
        # Test
        report = ConversationStorage.generate_analytics_report(format="csv")
        
        # Verify
        assert isinstance(report, str)
        assert 'Metric' in report
        assert 'Value' in report
        assert 'Total Conversations' in report
        assert 'Total Messages' in report
    
    # Prompt Template Tests
    def test_validate_prompt_template_valid(self):
        """Test validating a valid prompt template."""
        template = "You are a helpful assistant. User ID: {user_id}, Chat: {chat_id}"
        is_valid, error = ConversationStorage.validate_prompt_template(template)
        assert is_valid is True
        assert error is None
    
    def test_validate_prompt_template_unbalanced_braces(self):
        """Test validating template with unbalanced braces."""
        template = "Hello {user_id"
        is_valid, error = ConversationStorage.validate_prompt_template(template)
        assert is_valid is False
        assert "Unbalanced braces" in error
    
    def test_validate_prompt_template_nested_braces(self):
        """Test validating template with nested braces."""
        template = "Hello {{user_id}}"
        is_valid, error = ConversationStorage.validate_prompt_template(template)
        assert is_valid is False
        assert "Nested braces" in error
    
    def test_validate_prompt_template_invalid_variable(self):
        """Test validating template with invalid variable name."""
        template = "Hello {user-id}"
        is_valid, error = ConversationStorage.validate_prompt_template(template)
        assert is_valid is False
        assert "Invalid variable name" in error
    
    def test_validate_prompt_template_empty(self):
        """Test validating empty template."""
        is_valid, error = ConversationStorage.validate_prompt_template("")
        assert is_valid is False
        assert "cannot be empty" in error
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_create_prompt_template(self, mock_get_conn):
        """Test creating a prompt template."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ('template-123',)
        
        template_id = ConversationStorage.create_prompt_template(
            name="test_template",
            template_text="Hello {user_id}",
            user_id="user123"
        )
        
        assert template_id == "template-123"
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_create_prompt_template_invalid_syntax(self, mock_get_conn):
        """Test creating template with invalid syntax."""
        template_id = ConversationStorage.create_prompt_template(
            name="test_template",
            template_text="Hello {user-id}",  # Invalid variable name
            user_id="user123"
        )
        
        assert template_id is None
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_prompt_template(self, mock_get_conn):
        """Test getting a prompt template by ID."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'id': 'template-123',
            'name': 'test_template',
            'template_text': 'Hello {user_id}',
            'user_id': 'user123',
            'conversation_id': None,
            'description': 'Test template',
            'is_active': True,
            'created_at': '2025-01-01',
            'updated_at': '2025-01-01'
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        template = ConversationStorage.get_prompt_template("template-123")
        
        assert template is not None
        assert template['id'] == 'template-123'
        assert template['name'] == 'test_template'
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_prompt_template_not_found(self, mock_get_conn):
        """Test getting non-existent template."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None
        
        template = ConversationStorage.get_prompt_template("nonexistent")
        
        assert template is None
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_prompt_template_for_user(self, mock_get_conn):
        """Test getting user-specific template."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'id': 'template-123',
            'name': 'user_template',
            'template_text': 'User template',
            'user_id': 'user123',
            'conversation_id': None,
            'description': None,
            'is_active': True,
            'created_at': '2025-01-01',
            'updated_at': '2025-01-01'
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        template = ConversationStorage.get_prompt_template_for_user("user123")
        
        assert template is not None
        assert template['user_id'] == 'user123'
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_prompt_template_for_conversation(self, mock_get_conn):
        """Test getting conversation-specific template with fallback."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock conversation exists
        mock_conv_result = MagicMock()
        mock_conv_result.__getitem__.side_effect = lambda key: {
            'id': 'conv-123'
        }[key]
        
        # Mock conversation template
        mock_template_result = MagicMock()
        mock_template_result.__getitem__.side_effect = lambda key: {
            'id': 'template-123',
            'name': 'conv_template',
            'template_text': 'Conversation template',
            'user_id': 'user123',
            'conversation_id': 'conv-123',
            'description': None,
            'is_active': True,
            'created_at': '2025-01-01',
            'updated_at': '2025-01-01'
        }[key]
        
        mock_cursor.fetchone.side_effect = [mock_conv_result, mock_template_result]
        
        template = ConversationStorage.get_prompt_template_for_conversation("user123", "chat456")
        
        assert template is not None
        assert template['conversation_id'] == 'conv-123'
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_list_prompt_templates(self, mock_get_conn):
        """Test listing prompt templates."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_results = []
        for i in range(2):
            mock_result = MagicMock()
            mock_result.__getitem__.side_effect = lambda key, idx=i: {
                'id': f'template-{idx}',
                'name': f'template_{idx}',
                'template_text': f'Template {idx}',
                'user_id': None,
                'conversation_id': None,
                'description': None,
                'is_active': True,
                'created_at': '2025-01-01',
                'updated_at': '2025-01-01'
            }[key]
            mock_results.append(mock_result)
        
        mock_cursor.fetchall.return_value = mock_results
        
        templates = ConversationStorage.list_prompt_templates()
        
        assert len(templates) == 2
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_update_prompt_template(self, mock_get_conn):
        """Test updating a prompt template."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1
        
        success = ConversationStorage.update_prompt_template(
            template_id="template-123",
            template_text="Updated template",
            description="Updated description"
        )
        
        assert success is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_delete_prompt_template(self, mock_get_conn):
        """Test deleting a prompt template."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.rowcount = 1
        
        success = ConversationStorage.delete_prompt_template("template-123")
        
        assert success is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_export_conversation_json(self, mock_get_conn):
        """Test exporting conversation to JSON format."""
        from datetime import datetime
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock conversation result
        mock_conv = MagicMock()
        mock_conv.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'user_id': 'user-123',
            'session_id': 'chat-456',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'updated_at': datetime(2024, 1, 2, 12, 0, 0),
            'metadata': {'key': 'value'}
        }[key]
        mock_cursor.fetchone.return_value = mock_conv
        
        # Mock messages
        mock_msg1 = MagicMock()
        mock_msg1.__getitem__.side_effect = lambda key: {
            'role': 'user',
            'content': 'Hello',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'metadata': {}
        }[key]
        mock_msg2 = MagicMock()
        mock_msg2.__getitem__.side_effect = lambda key: {
            'role': 'assistant',
            'content': 'Hi there!',
            'created_at': datetime(2024, 1, 1, 12, 1, 0),
            'metadata': {}
        }[key]
        mock_cursor.fetchall.return_value = [mock_msg1, mock_msg2]
        
        # Test
        result = ConversationStorage.export_conversation("user-123", "chat-456", format="json")
        
        # Verify
        assert isinstance(result, bytes)
        data = json.loads(result.decode('utf-8'))
        assert data['conversation_id'] == 'conv-123'
        assert data['user_id'] == 'user-123'
        assert data['chat_id'] == 'chat-456'
        assert data['message_count'] == 2
        assert len(data['messages']) == 2
        assert data['messages'][0]['role'] == 'user'
        assert data['messages'][0]['content'] == 'Hello'
        assert data['messages'][1]['role'] == 'assistant'
        assert data['messages'][1]['content'] == 'Hi there!'
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_export_conversation_txt(self, mock_get_conn):
        """Test exporting conversation to TXT format."""
        from datetime import datetime
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock conversation result
        mock_conv = MagicMock()
        mock_conv.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'user_id': 'user-123',
            'session_id': 'chat-456',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'updated_at': datetime(2024, 1, 2, 12, 0, 0),
            'metadata': {}
        }[key]
        mock_cursor.fetchone.return_value = mock_conv
        
        # Mock messages
        mock_msg = MagicMock()
        mock_msg.__getitem__.side_effect = lambda key: {
            'role': 'user',
            'content': 'Test message',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'metadata': {}
        }[key]
        mock_cursor.fetchall.return_value = [mock_msg]
        
        # Test
        result = ConversationStorage.export_conversation("user-123", "chat-456", format="txt")
        
        # Verify
        assert isinstance(result, bytes)
        text = result.decode('utf-8')
        assert 'Conversation Export' in text
        assert 'user-123' in text
        assert 'chat-456' in text
        assert 'Test message' in text
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_export_conversation_pdf(self, mock_get_conn):
        """Test exporting conversation to PDF format."""
        from datetime import datetime
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock conversation result
        mock_conv = MagicMock()
        mock_conv.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'user_id': 'user-123',
            'session_id': 'chat-456',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'updated_at': datetime(2024, 1, 2, 12, 0, 0),
            'metadata': {}
        }[key]
        mock_cursor.fetchone.return_value = mock_conv
        
        # Mock messages
        mock_msg = MagicMock()
        mock_msg.__getitem__.side_effect = lambda key: {
            'role': 'user',
            'content': 'Test message',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'metadata': {}
        }[key]
        mock_cursor.fetchall.return_value = [mock_msg]
        
        # Test
        result = ConversationStorage.export_conversation("user-123", "chat-456", format="pdf")
        
        # Verify
        assert isinstance(result, bytes)
        # PDF files start with %PDF
        assert result.startswith(b'%PDF')
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_export_conversation_not_found(self, mock_get_conn):
        """Test exporting conversation when conversation doesn't exist."""
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock no conversation found
        mock_cursor.fetchone.return_value = None
        
        # Test - should raise ValueError
        with pytest.raises(ValueError, match="Conversation not found"):
            ConversationStorage.export_conversation("user-123", "chat-456", format="json")
        
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_export_conversation_invalid_format(self, mock_get_conn):
        """Test exporting conversation with invalid format."""
        from datetime import datetime
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock conversation result
        mock_conv = MagicMock()
        mock_conv.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'user_id': 'user-123',
            'session_id': 'chat-456',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'updated_at': datetime(2024, 1, 2, 12, 0, 0),
            'metadata': {}
        }[key]
        mock_cursor.fetchone.return_value = mock_conv
        mock_cursor.fetchall.return_value = []
        
        # Test - should raise ValueError
        with pytest.raises(ValueError, match="Unsupported export format"):
            ConversationStorage.export_conversation("user-123", "chat-456", format="invalid")
        
        mock_conn.close.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_export_conversation_with_date_filter(self, mock_get_conn):
        """Test exporting conversation with date range filter."""
        from datetime import datetime
        
        # Mock database connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        # Mock conversation result
        mock_conv = MagicMock()
        mock_conv.__getitem__.side_effect = lambda key: {
            'id': 'conv-123',
            'user_id': 'user-123',
            'session_id': 'chat-456',
            'created_at': datetime(2024, 1, 1, 12, 0, 0),
            'updated_at': datetime(2024, 1, 2, 12, 0, 0),
            'metadata': {}
        }[key]
        mock_cursor.fetchone.return_value = mock_conv
        
        # Mock messages
        mock_cursor.fetchall.return_value = []
        
        # Test with date filters
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 12, 31)
        result = ConversationStorage.export_conversation(
            "user-123", "chat-456", format="json",
            start_date=start_date, end_date=end_date
        )
        
        # Verify
        assert isinstance(result, bytes)
        # Verify that execute was called with date filters (check SQL contains date conditions)
        # The execute should be called twice: once for conversation, once for messages
        assert mock_cursor.execute.call_count >= 2
        mock_conn.close.assert_called_once()
    
    # ==================== A/B Testing Tests ====================
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_create_ab_test(self, mock_get_conn):
        """Test creating an A/B test."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = ['test-uuid-123']
        
        variants = [
            {"name": "A", "model": "gpt-4", "temperature": 0.7, "system_prompt": "You are helpful."},
            {"name": "B", "model": "gpt-3.5", "temperature": 0.9, "system_prompt": "You are creative."}
        ]
        
        result = ConversationStorage.create_ab_test(
            name="test_ab",
            variants=variants,
            description="Test A/B test",
            traffic_split=0.5
        )
        
        assert result == "test-uuid-123"
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_ab_test(self, mock_get_conn):
        """Test getting an A/B test."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'id': 'test-uuid-123',
            'name': 'test_ab',
            'description': 'Test',
            'variants': json.dumps([{"name": "A"}, {"name": "B"}]),
            'traffic_split': 1.0,
            'is_active': True,
            'created_at': '2024-01-01',
            'updated_at': '2024-01-01'
        }[key]
        mock_cursor.fetchone.return_value = mock_result
        
        result = ConversationStorage.get_ab_test("test-uuid-123")
        
        assert result is not None
        assert result['name'] == 'test_ab'
        assert isinstance(result['variants'], list)
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_list_ab_tests(self, mock_get_conn):
        """Test listing A/B tests."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_result1 = MagicMock()
        mock_result1.__getitem__.side_effect = lambda key: {
            'id': 'test-1',
            'name': 'test1',
            'variants': json.dumps([{"name": "A"}]),
            'is_active': True
        }[key]
        mock_result2 = MagicMock()
        mock_result2.__getitem__.side_effect = lambda key: {
            'id': 'test-2',
            'name': 'test2',
            'variants': json.dumps([{"name": "B"}]),
            'is_active': False
        }[key]
        mock_cursor.fetchall.return_value = [mock_result1, mock_result2]
        
        result = ConversationStorage.list_ab_tests(active_only=False)
        
        assert len(result) == 2
        assert result[0]['name'] == 'test1'
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_assign_ab_variant(self, mock_get_conn):
        """Test assigning A/B test variant to conversation."""
        # Mock get_ab_test first
        with patch.object(ConversationStorage, 'get_ab_test') as mock_get_test:
            mock_get_test.return_value = {
                'is_active': True,
                'variants': [
                    {"name": "A", "model": "gpt-4"},
                    {"name": "B", "model": "gpt-3.5"}
                ],
                'traffic_split': 1.0
            }
            
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = None  # No existing assignment
            mock_cursor.fetchone.side_effect = [None, None]  # No existing, then after insert
            
            result = ConversationStorage.assign_ab_variant(
                test_id="test-123",
                conversation_id="conv-456"
            )
            
            # Should assign a variant (A or B)
            assert result in ["A", "B"]
            mock_cursor.execute.assert_called()
            mock_conn.commit.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_record_ab_metric(self, mock_get_conn):
        """Test recording A/B test metric."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        result = ConversationStorage.record_ab_metric(
            test_id="test-123",
            variant_name="A",
            metric_type="response_time",
            metric_value=1.5,
            conversation_id="conv-456"
        )
        
        assert result is True
        mock_cursor.execute.assert_called_once()
        mock_conn.commit.assert_called_once()
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_ab_metrics(self, mock_get_conn):
        """Test getting A/B test metrics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        
        mock_result = MagicMock()
        mock_result.__getitem__.side_effect = lambda key: {
            'variant_name': 'A',
            'metric_type': 'response_time',
            'metric_value': 1.5,
            'conversation_id': 'conv-456',
            'metadata': '{}',
            'recorded_at': '2024-01-01'
        }[key]
        mock_cursor.fetchall.return_value = [mock_result]
        
        result = ConversationStorage.get_ab_metrics(
            test_id="test-123",
            variant_name="A",
            metric_type="response_time"
        )
        
        assert len(result) == 1
        assert result[0]['variant_name'] == 'A'
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_ab_statistics(self, mock_get_conn):
        """Test getting A/B test statistics."""
        with patch.object(ConversationStorage, 'get_ab_test') as mock_get_test:
            mock_get_test.return_value = {
                'name': 'test_ab',
                'variants': [
                    {"name": "A"},
                    {"name": "B"}
                ]
            }
            
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            
            mock_metric = MagicMock()
            mock_metric.__getitem__.side_effect = lambda key: {
                'metric_type': 'response_time',
                'metric_value': 1.5,
                'count': 10
            }[key]
            mock_cursor.fetchall.return_value = [mock_metric]
            
            result = ConversationStorage.get_ab_statistics("test-123")
            
            assert 'variants' in result
            assert 'A' in result['variants']
            assert 'B' in result['variants']
    
    @patch('essence.services.telegram.conversation_storage.get_db_connection')
    def test_get_ab_test_variant_config(self, mock_get_conn):
        """Test getting A/B test variant configuration."""
        with patch.object(ConversationStorage, 'assign_ab_variant') as mock_assign, \
             patch.object(ConversationStorage, 'get_ab_test') as mock_get_test:
            
            mock_assign.return_value = "A"
            mock_get_test.return_value = {
                'variants': [
                    {"name": "A", "model": "gpt-4", "temperature": 0.7}
                ]
            }
            
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_get_conn.return_value = mock_conn
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = {'id': 'conv-123'}
            
            result = ConversationStorage.get_ab_test_variant_config(
                user_id="user-123",
                chat_id="chat-456",
                ab_test_id="test-123"
            )
            
            assert result is not None
            assert result['conversation_id'] == 'conv-123'
            assert result['variant_name'] == 'A'
            assert result['variant_config'] is not None
