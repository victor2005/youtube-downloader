import os
import time
import logging
import threading
from pathlib import Path
from datetime import datetime, timedelta
import shutil
import psutil

class ResourceManager:
    def __init__(self, app):
        self.app = app
        self.downloads_dir = Path('downloads')
        self.max_file_age_hours = 24  # Files older than 24 hours will be deleted
        self.max_disk_usage_gb = 5  # Maximum total disk usage in GB
        self.max_concurrent_downloads = 3  # Maximum concurrent downloads per user
        self.cleanup_interval = 1800  # Run cleanup every 30 minutes
        self.user_concurrent_downloads = {}  # Track concurrent downloads per user
        
        # Start background cleanup thread
        self.cleanup_thread = threading.Thread(target=self._background_cleanup, daemon=True)
        self.cleanup_thread.start()
        
        logging.info("Resource Manager initialized")
    
    def can_start_download(self, user_id):
        """Check if user can start a new download"""
        current_downloads = self.user_concurrent_downloads.get(user_id, 0)
        if current_downloads >= self.max_concurrent_downloads:
            logging.warning(f"User {user_id} exceeded concurrent download limit ({current_downloads}/{self.max_concurrent_downloads})")
            return False
        return True
    
    def start_download(self, user_id):
        """Mark start of download for user"""
        if user_id not in self.user_concurrent_downloads:
            self.user_concurrent_downloads[user_id] = 0
        self.user_concurrent_downloads[user_id] += 1
        logging.info(f"User {user_id} started download. Current: {self.user_concurrent_downloads[user_id]}")
    
    def finish_download(self, user_id):
        """Mark end of download for user"""
        if user_id in self.user_concurrent_downloads:
            self.user_concurrent_downloads[user_id] = max(0, self.user_concurrent_downloads[user_id] - 1)
            if self.user_concurrent_downloads[user_id] == 0:
                del self.user_concurrent_downloads[user_id]
            logging.info(f"User {user_id} finished download. Remaining: {self.user_concurrent_downloads.get(user_id, 0)}")
    
    def check_disk_space(self):
        """Check if we have enough disk space"""
        try:
            # Get total size of downloads directory
            total_size = 0
            if self.downloads_dir.exists():
                for dirpath, dirnames, filenames in os.walk(self.downloads_dir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            total_size += os.path.getsize(filepath)
                        except (OSError, FileNotFoundError):
                            pass
            
            size_gb = total_size / (1024**3)
            if size_gb > self.max_disk_usage_gb:
                logging.warning(f"Disk usage exceeded limit: {size_gb:.2f}GB > {self.max_disk_usage_gb}GB")
                return False
            
            # Also check available disk space
            disk_usage = shutil.disk_usage(self.downloads_dir.parent if self.downloads_dir.exists() else '.')
            free_gb = disk_usage.free / (1024**3)
            if free_gb < 1:  # Less than 1GB free
                logging.warning(f"Low disk space: {free_gb:.2f}GB remaining")
                return False
            
            return True
        except Exception as e:
            logging.error(f"Error checking disk space: {e}")
            return False
    
    def cleanup_user_files(self, user_id):
        """Clean up old files for a specific user"""
        user_dir = self.downloads_dir / user_id
        if not user_dir.exists():
            return
        
        files_removed = 0
        total_size_removed = 0
        cutoff_time = time.time() - (self.max_file_age_hours * 3600)
        
        try:
            # Get all files with their timestamps
            files_with_time = []
            for file_path in user_dir.iterdir():
                if file_path.is_file():
                    try:
                        stat = file_path.stat()
                        files_with_time.append((file_path, stat.st_mtime, stat.st_size))
                    except (OSError, FileNotFoundError):
                        pass
            
            # Sort by modification time (oldest first)
            files_with_time.sort(key=lambda x: x[1])
            
            # Remove old files
            for file_path, mtime, size in files_with_time:
                if mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        files_removed += 1
                        total_size_removed += size
                        logging.info(f"Removed old file: {file_path.name} ({size} bytes)")
                    except (OSError, FileNotFoundError):
                        pass
            
            # If still too many files, remove oldest ones
            remaining_files = [f for f in files_with_time if f[1] >= cutoff_time]
            while len(remaining_files) > self.max_user_files:
                file_path, mtime, size = remaining_files.pop(0)
                try:
                    file_path.unlink()
                    files_removed += 1
                    total_size_removed += size
                    logging.info(f"Removed excess file: {file_path.name} ({size} bytes)")
                except (OSError, FileNotFoundError):
                    pass
            
            # Remove empty directory
            if not any(user_dir.iterdir()):
                user_dir.rmdir()
                logging.info(f"Removed empty user directory: {user_id}")
            
            if files_removed > 0:
                logging.info(f"Cleaned up {files_removed} files for user {user_id}, freed {total_size_removed / (1024*1024):.2f}MB")
        
        except Exception as e:
            logging.error(f"Error cleaning up files for user {user_id}: {e}")
    
    def cleanup_all_users(self):
        """Clean up files for all users"""
        if not self.downloads_dir.exists():
            return
        
        for user_dir in self.downloads_dir.iterdir():
            if user_dir.is_dir():
                self.cleanup_user_files(user_dir.name)
    
    def cleanup_memory(self, download_progress, user_downloads, progress_timestamps):
        """Clean up old data from memory"""
        current_time = time.time()
        old_threshold = 3600  # 1 hour
        
        # Clean up old progress data
        old_downloads = []
        for download_id, timestamp in progress_timestamps.items():
            if current_time - timestamp > old_threshold:
                old_downloads.append(download_id)
        
        for download_id in old_downloads:
            download_progress.pop(download_id, None)
            progress_timestamps.pop(download_id, None)
        
        if old_downloads:
            logging.info(f"Cleaned up {len(old_downloads)} old download progress entries")
        
        # Clean up user downloads data for users with no files
        empty_users = []
        for user_id, files in user_downloads.items():
            user_dir = self.downloads_dir / user_id
            if not user_dir.exists() or not any(user_dir.iterdir()):
                empty_users.append(user_id)
        
        for user_id in empty_users:
            user_downloads.pop(user_id, None)
        
        if empty_users:
            logging.info(f"Cleaned up {len(empty_users)} empty user download entries")
    
    def get_system_stats(self):
        """Get current system resource usage"""
        try:
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage for downloads directory
            downloads_size = 0
            if self.downloads_dir.exists():
                for dirpath, dirnames, filenames in os.walk(self.downloads_dir):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        try:
                            downloads_size += os.path.getsize(filepath)
                        except (OSError, FileNotFoundError):
                            pass
            
            return {
                'memory_percent': memory.percent,
                'memory_available_gb': memory.available / (1024**3),
                'downloads_size_gb': downloads_size / (1024**3),
                'concurrent_downloads': sum(self.user_concurrent_downloads.values()),
                'active_users': len(self.user_concurrent_downloads)
            }
        except Exception as e:
            logging.error(f"Error getting system stats: {e}")
            return None
    
    def _background_cleanup(self):
        """Background thread for periodic cleanup"""
        while True:
            try:
                time.sleep(self.cleanup_interval)
                logging.info("Starting background cleanup...")
                
                # Clean up files
                self.cleanup_all_users()
                
                # Get references to app's data structures
                with self.app.app_context():
                    # Import here to avoid circular imports
                    from app import download_progress, user_downloads, progress_timestamps
                    self.cleanup_memory(download_progress, user_downloads, progress_timestamps)
                
                stats = self.get_system_stats()
                if stats:
                    logging.info(f"System stats after cleanup: "
                               f"Memory: {stats['memory_percent']:.1f}%, "
                               f"Downloads: {stats['downloads_size_gb']:.2f}GB, "
                               f"Active downloads: {stats['concurrent_downloads']}")
                
                logging.info("Background cleanup completed")
                
            except Exception as e:
                logging.error(f"Error in background cleanup: {e}")
