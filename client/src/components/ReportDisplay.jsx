import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { motion } from 'framer-motion';

function ReportDisplay({ isLoading, error, reportData }) {
  if (isLoading) {
    return <div className="loading-spinner"></div>;
  }

  if (error) {
    return <div className="error-box">{error}</div>;
  }

  if (reportData && reportData.markdown) {
    return (
      <motion.main
            className="report-container"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
        >

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
      </motion.main>
    );
  }
  
  return null;
}

export default ReportDisplay;