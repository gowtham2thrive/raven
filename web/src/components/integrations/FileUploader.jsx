import { useState, useRef, useCallback } from 'react';
import { 
  IconUpload, 
  IconFileText, 
  IconCheckCircle, 
  IconRefreshCw, 
  IconX
} from '../Icons';

function formatFileSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileUploader({ accept = '*', onFileSelect, fileMetadata, onClear }) {
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef(null);

  const handleFile = useCallback(async (file) => {
    setUploading(true);
    try {
      await onFileSelect(file);
    } finally {
      setUploading(false);
    }
  }, [onFileSelect]);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer?.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleInputChange = (e) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="file-uploader-container">
      <div
        className={`file-drop-zone ${dragOver ? 'drag-over' : ''} ${uploading ? 'uploading' : ''}`}
        onClick={() => !uploading && inputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && !uploading && inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          onChange={handleInputChange}
          style={{ display: 'none' }}
        />

        {uploading ? (
          <div className="file-drop-zone-content">
            <div className="drop-zone-icon-circle spinning">
              <IconRefreshCw className="spin" size={24} />
            </div>
            <div className="drop-zone-primary-text">Uploading & Parsing Document...</div>
            <div className="drop-zone-hint-text">Extracting schema and validating columns</div>
          </div>
        ) : (
          <div className="file-drop-zone-content">
            <div className="drop-zone-icon-circle">
              <IconUpload size={24} />
            </div>
            <div className="drop-zone-primary-text">
              Drop your evidence file here, or <span className="browse-link">browse</span>
            </div>
            <div className="drop-zone-hint-text">
              Accepted formats: <strong>{accept === '*' ? 'CSV, Excel (.xlsx, .xls), PDF' : accept}</strong>
            </div>
          </div>
        )}
      </div>

      {fileMetadata && (
        <div className="file-selected-card">
          <div className="file-selected-info">
            <div className="file-icon-box">
              <IconFileText size={18} />
            </div>
            <div className="file-text-meta">
              <div className="file-name-row">
                <span className="file-name">{fileMetadata.filename}</span>
                <span className="file-success-tag">
                  <IconCheckCircle size={12} /> Ready
                </span>
              </div>
              <div className="file-size-row">
                <span>{formatFileSize(fileMetadata.file_size_bytes)}</span>
                {fileMetadata.sheet_names && fileMetadata.sheet_names.length > 0 && (
                  <span>· Sheet: {fileMetadata.sheet_names[0]}</span>
                )}
              </div>
            </div>
          </div>

          {onClear && (
            <button 
              type="button" 
              className="btn-clear-file" 
              onClick={(e) => {
                e.stopPropagation();
                onClear();
              }}
              title="Remove file"
            >
              <IconX size={14} />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
