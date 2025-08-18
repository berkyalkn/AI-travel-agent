import React from 'react';
import { motion } from 'framer-motion';
import { FaPlaneDeparture } from "react-icons/fa";

function InputForm({ formData, setFormData, handlePlanTrip, isLoading, errors }) {
  
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prevData => ({ ...prevData, [name]: value }));
  };

  return (
    <div className="guided-form">
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="destination">To (Destination)</label>
          <input type="text" id="destination" name="destination" value={formData.destination} onChange={handleChange} placeholder="e.g., Rome" disabled={isLoading} className={errors.destination ? "input-error" : ""} />
          {errors.destination && <p className="error-message">{errors.destination}</p>}
        </div>
        <div className="form-group">
          <label htmlFor="origin">From (Origin)</label>
          <input type="text" id="origin" name="origin" value={formData.origin} onChange={handleChange} placeholder="e.g., Istanbul" disabled={isLoading} className={errors.origin ? "input-error" : ""}/>
          {errors.origin && <p className="error-message">{errors.origin}</p>}
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="dates">Dates</label>
          <input type="text" id="dates" name="dates" value={formData.dates} onChange={handleChange} placeholder="e.g., 2026-10-15 to 2026-10-20" disabled={isLoading} className={errors.dates ? "input-error" : ""}/>
          {errors.dates && <p className="error-message">{errors.dates}</p>}
        </div>
        <div className="form-group">
          <label htmlFor="people">Number of People</label>
          <input type="text" id="people" name="people" value={formData.people} onChange={handleChange} placeholder="e.g., 2" disabled={isLoading} className={errors.people ? "input-error" : ""}/>
          {errors.people && <p className="error-message">{errors.people}</p>}
        </div>
      </div>
      <div className="form-group full-width">
        <label htmlFor="interests">Interests</label>
        <input type="text" id="interests" name="interests" value={formData.interests} onChange={handleChange} placeholder="e.g., history, art, food" disabled={isLoading} className={errors.interests ? "input-error" : ""}/>
        {errors.interests && <p className="error-message">{errors.interests}</p>}
      </div>
      <div className="form-group full-width">
        <label htmlFor="budget">Budget</label>
        <input type="text" id="budget" name="budget" value={formData.budget} onChange={handleChange} placeholder="e.g., 2000 euros" disabled={isLoading} className={errors.budget ? "input-error" : ""}/>
        {errors.budget && <p className="error-message">{errors.budget}</p>}
      </div>
      
    
      <div className="form-submit-area">
        <motion.button
          whileTap={{ scale: 0.95 }}
          whileHover={{ scale: 1.05 }}
          disabled={isLoading}
          onClick={handlePlanTrip}
          className="plan-button" 
        >
          {isLoading ? (
            <motion.div
              initial={{ y: 0 }}
              animate={{ y: -5 }} 
              transition={{
                repeat: Infinity,
                repeatType: "reverse",
                duration: 0.5,
                ease: "easeInOut"
              }}
              className="loading-button-content"
            >
              <FaPlaneDeparture />
              <span>Taking off...</span>
            </motion.div>
          ) : (
            "Plan My Trip"
          )}
        </motion.button>
      </div>
    </div>
  );
}

export default InputForm;