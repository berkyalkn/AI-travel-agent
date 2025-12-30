import React from 'react';
import { FaPlaneDeparture } from 'react-icons/fa';

function Header() {
  return (
    <header className="App-header gradient-header">
      <div className="title-container">
        <h1> AI Travel Agent</h1>
        <FaPlaneDeparture className="plane-icon" />
      </div>
      <p>Describe your trip, and I'll create a detailed itinerary for you.</p>
      <div className="decorative-line"></div>
    </header>
  );
}

export default Header;