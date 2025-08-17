import React from 'react';

function Header() {
  return (
    <header className="App-header">
      <div className="title-container">
        <h1>AI Travel Agent</h1>
        <span className="plane-icon">✈️</span>
      </div>
      <p>Describe your trip, and I'll create a detailed itinerary for you.</p>
    </header>
  );
}

export default Header;