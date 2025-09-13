import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

function ReportDisplay({ isLoading, error, reportData }) {
  if (isLoading) {
    return <div className="loading-spinner"></div>;
  }

  if (error) {
    return <div className="error-box">{error}</div>;
  }

  if (reportData && reportData.markdown) {
    return (
      <main className="report-container">
        <div className="markdown-content">
          <ReactMarkdown 
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            >
            {reportData.markdown}
          </ReactMarkdown>
        
          {reportData.map && (
            <div 
              style={{
                border: '1px solid #e1e1e1',
                borderRadius: '8px',
                overflow: 'hidden',
                height: '500px',
                marginTop: '2rem'
              }}
            >
              <iframe
                srcDoc={reportData.map}
                title="Trip Itinerary Map"
                style={{ border: 'none', width: '100%', height: '100%' }}
                sandbox="allow-scripts allow-same-origin"
              />
            </div>
          )}
        </div>
      </main>
    );
  }
  
  return null;
}

export default ReportDisplay;