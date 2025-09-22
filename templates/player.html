<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mraprguild Media Player</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }
    
    body {
      background: linear-gradient(135deg, 
                  rgba(26, 42, 108, 0.15), 
                  rgba(42, 58, 124, 0.15), 
                  rgba(58, 74, 140, 0.15)), 
                  url('https://images.unsplash.com/photo-1470225620780-dba8ba36b745?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80') center/cover no-repeat;
      color: #fff;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      padding: 20px;
      transition: background-image 1.5s ease-in-out;
      overflow: hidden;
      position: relative;
    }
    
    body::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(10, 10, 20, 0.7);
      z-index: -1;
    }
    
    .container {
      width: 100%;
      max-width: 1200px; /* Increased from 900px */
      background: rgba(25, 25, 35, 0.25);
      border-radius: 20px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
      overflow: hidden;
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.15);
      position: relative;
      z-index: 1;
    }
    
    .glass-effect {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(135deg, 
                  rgba(255, 255, 255, 0.1) 0%, 
                  rgba(255, 255, 255, 0.05) 100%);
      pointer-events: none;
      z-index: -1;
    }
    
    header {
      padding: 20px;
      text-align: center;
      background: rgba(15, 15, 25, 0.3);
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      position: relative;
    }
    
    h1 {
      font-size: 2.2rem;
      margin-bottom: 5px;
      background: linear-gradient(to right, #ffffff, #a0d2ff);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      text-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
      font-weight: 300;
      letter-spacing: 1px;
    }
    
    .subtitle {
      color: rgba(255, 255, 255, 0.7);
      font-size: 1rem;
      margin-bottom: 10px;
      font-weight: 300;
    }
    
    .player-container {
      padding: 25px;
      display: flex;
      flex-direction: column;
      align-items: center;
    }
    
    .media-display {
      width: 100%;
      max-width: 100%;
      margin-bottom: 25px;
      border-radius: 15px;
      overflow: hidden;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
      background: rgba(0, 0, 0, 0.3);
      position: relative;
      border: 1px solid rgba(255, 255, 255, 0.15);
      max-height: 80vh; /* Increased from 70vh */
    }
    
    video, audio, img {
      width: 100%;
      display: block;
      max-height: 80vh; /* Increased from 70vh */
    }
    
    .custom-audio-player {
      width: 100%;
      padding: 15px;
      background: rgba(26, 26, 42, 0.3);
      border-radius: 10px;
      position: relative;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .custom-video-controls {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(0, 0, 0, 0.6);
      padding: 15px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 15px;
      opacity: 0;
      transition: opacity 0.3s ease;
      backdrop-filter: blur(10px);
      border-top: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .media-display:hover .custom-video-controls {
      opacity: 1;
    }
    
    .control-btn {
      background: rgba(255, 255, 255, 0.15);
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: white;
      width: 45px;
      height: 45px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.2s ease;
      backdrop-filter: blur(5px);
    }
    
    .control-btn:hover {
      background: rgba(255, 255, 255, 0.25);
      transform: scale(1.1);
      box-shadow: 0 0 15px rgba(100, 180, 255, 0.5);
    }
    
    .control-btn i {
      font-size: 18px;
    }
    
    .skip-btn {
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: white;
      padding: 10px 15px;
      border-radius: 25px;
      display: flex;
      align-items: center;
      gap: 5px;
      cursor: pointer;
      transition: all 0.2s ease;
      font-weight: 600;
      backdrop-filter: blur(5px);
    }
    
    .skip-btn:hover {
      background: rgba(255, 255, 255, 0.2);
      box-shadow: 0 0 10px rgba(100, 180, 255, 0.3);
    }
    
    .media-info {
      padding: 15px;
      background: rgba(30, 30, 45, 0.3);
      border-radius: 12px;
      margin-bottom: 20px;
      width: 100%;
      font-size: 0.9rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border: 1px solid rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(10px);
    }
    
    .media-type {
      background: linear-gradient(135deg, rgba(79, 172, 254, 0.4), rgba(79, 172, 254, 0.2));
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 0.8rem;
      font-weight: bold;
      border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .media-category {
      background: linear-gradient(135deg, rgba(255, 159, 28, 0.4), rgba(255, 159, 28, 0.2));
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 0.8rem;
      font-weight: bold;
      border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .controls {
      display: flex;
      gap: 15px;
      margin-top: 15px;
      flex-wrap: wrap;
      justify-content: center;
    }
    
    .btn {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 12px 20px;
      background: rgba(255, 255, 255, 0.15);
      color: white;
      text-decoration: none;
      border-radius: 50px;
      font-weight: 600;
      transition: all 0.3s ease;
      box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
      cursor: pointer;
      border: 1px solid rgba(255, 255, 255, 0.2);
      backdrop-filter: blur(10px);
      position: relative;
      overflow: hidden;
    }
    
    .btn::before {
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
      transition: left 0.5s;
    }
    
    .btn:hover::before {
      left: 100%;
    }
    
    .btn:hover {
      transform: translateY(-3px);
      box-shadow: 0 8px 25px rgba(0, 0, 0, 0.3);
      background: rgba(255, 255, 255, 0.25);
    }
    
    .btn i {
      font-size: 1rem;
    }
    
    .loading {
      padding: 40px;
      text-align: center;
      color: rgba(255, 255, 255, 0.7);
    }
    
    .loading i {
      font-size: 2rem;
      margin-bottom: 15px;
      color: rgba(79, 172, 254, 0.7);
    }
    
    .error {
      padding: 30px;
      text-align: center;
      background: rgba(200, 60, 60, 0.2);
      border-radius: 10px;
      margin: 20px 0;
      border: 1px solid rgba(255, 100, 100, 0.3);
      backdrop-filter: blur(10px);
    }
    
    .error i {
      font-size: 2.5rem;
      margin-bottom: 15px;
      color: rgba(255, 107, 107, 0.7);
    }
    
    .background-selector {
      margin-top: 15px;
      width: 100%;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    
    .background-label {
      font-size: 0.9rem;
      color: rgba(255, 255, 255, 0.7);
      text-align: center;
    }
    
    .background-options {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: center;
    }
    
    .bg-option {
      width: 60px;
      height: 60px;
      border-radius: 8px;
      overflow: hidden;
      cursor: pointer;
      border: 2px solid transparent;
      transition: all 0.2s ease;
      position: relative;
    }
    
    .bg-option:hover {
      transform: scale(1.05);
    }
    
    .bg-option.active {
      border-color: rgba(79, 172, 254, 0.7);
      box-shadow: 0 0 15px rgba(79, 172, 254, 0.5);
    }
    
    .bg-option img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    
    footer {
      text-align: center;
      padding: 20px;
      color: rgba(255, 255, 255, 0.7);
      font-size: 0.9rem;
      border-top: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Player options modal */
    .modal {
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.7);
      z-index: 1000;
      justify-content: center;
      align-items: center;
      backdrop-filter: blur(10px);
    }
    
    .modal-content {
      background: rgba(35, 35, 50, 0.7);
      padding: 25px;
      border-radius: 20px;
      width: 90%;
      max-width: 500px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.15);
    }
    
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }
    
    .modal-title {
      font-size: 1.5rem;
      background: linear-gradient(to right, #ffffff, #a0d2ff);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    
    .close-modal {
      background: none;
      border: none;
      color: rgba(255, 255, 255, 0.7);
      font-size: 1.5rem;
      cursor: pointer;
      width: 35px;
      height: 35px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
    }
    
    .close-modal:hover {
      background: rgba(255, 255, 255, 0.1);
    }
    
    .player-options {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      gap: 15px;
      margin: 20px 0;
    }
    
    .player-option {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 15px;
      background: rgba(25, 25, 35, 0.5);
      border-radius: 15px;
      transition: all 0.3s ease;
      cursor: pointer;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .player-option:hover {
      transform: translateY(-5px);
      background: rgba(35, 35, 50, 0.7);
      box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
    }
    
    .player-icon {
      font-size: 2rem;
      margin-bottom: 10px;
    }
    
    .player-name {
      font-size: 0.9rem;
      text-align: center;
    }
    
    .download-info {
      margin-top: 20px;
      padding: 15px;
      background: rgba(30, 30, 45, 0.5);
      border-radius: 10px;
      font-size: 0.9rem;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Floating particles for high-tech effect */
    .particles {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 0;
      pointer-events: none;
    }
    
    .particle {
      position: absolute;
      width: 2px;
      height: 2px;
      background: rgba(255, 255, 255, 0.5);
      border-radius: 50%;
      animation: float 15s infinite linear;
    }
    
    @keyframes float {
      0% {
        transform: translateY(100vh) translateX(0);
        opacity: 0;
      }
      10% {
        opacity: 1;
      }
      90% {
        opacity: 1;
      }
      100% {
        transform: translateY(-100px) translateX(20px);
        opacity: 0;
      }
    }
    
    /* Progress bar for video/audio */
    .progress-container {
      width: 100%;
      height: 5px;
      background: rgba(255, 255, 255, 0.1);
      border-radius: 5px;
      margin: 10px 0;
      overflow: hidden;
      cursor: pointer;
    }
    
    .progress-bar {
      height: 100%;
      background: linear-gradient(90deg, #4facfe, #00f2fe);
      border-radius: 5px;
      width: 0%;
      transition: width 0.1s;
    }
    
    /* New styles for skip buttons and subtitle/audio controls */
    .skip-controls {
      display: flex;
      gap: 15px;
      margin: 15px 0;
      justify-content: center;
      flex-wrap: wrap;
    }
    
    .subtitle-controls, .audio-controls {
      display: flex;
      gap: 10px;
      align-items: center;
      margin: 10px 0;
      flex-wrap: wrap;
      justify-content: center;
    }
    
    .control-label {
      font-size: 0.9rem;
      color: rgba(255, 255, 255, 0.8);
      font-weight: 500;
    }
    
    .control-select {
      background: rgba(255, 255, 255, 0.15);
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: white;
      padding: 8px 12px;
      border-radius: 20px;
      cursor: pointer;
      backdrop-filter: blur(5px);
      transition: all 0.2s ease;
    }
    
    .control-select:hover {
      background: rgba(255, 255, 255, 0.25);
    }
    
    .control-select option {
      background: rgba(30, 30, 45, 0.9);
      color: white;
    }
    
    .subtitle-display {
      position: absolute;
      bottom: 80px;
      left: 0;
      right: 0;
      text-align: center;
      padding: 10px;
      background: rgba(0, 0, 0, 0.7);
      color: white;
      font-size: 1.1rem;
      text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.8);
      backdrop-filter: blur(5px);
      transition: opacity 0.3s ease;
      z-index: 5;
    }
    
    @media (max-width: 600px) {
      .container {
        border-radius: 15px;
      }
      
      h1 {
        font-size: 1.8rem;
      }
      
      .player-container {
        padding: 15px;
      }
      
      .controls {
        flex-direction: column;
        width: 100%;
      }
      
      .btn {
        width: 100%;
        justify-content: center;
      }
      
      .player-options {
        grid-template-columns: 1fr 1fr;
      }
      
      .background-options {
        justify-content: center;
      }
      
      .skip-controls {
        flex-direction: column;
        align-items: center;
      }
      
      .subtitle-controls, .audio-controls {
        flex-direction: column;
      }
    }
  </style>
</head>
<body>
  <div class="particles" id="particles"></div>
  
  <div class="container">
    <div class="glass-effect"></div>
    
    <header>
      <h1>Mraprguild Media Player</h1>
      <div class="subtitle">Immersive High-Tech Media Experience</div>
    </header>
    
    <div class="player-container">
      <div class="media-info">
        <div class="media-url">Content from secure source</div>
        <div class="media-type">Loading...</div>
        <div class="media-category">Detecting...</div>
      </div>
      
      <div id="player" class="media-display">
        <div class="loading">
          <i class="fas fa-spinner fa-spin"></i>
          <p>Loading your media content...</p>
        </div>
      </div>
      
      <!-- Skip buttons below the player -->
      <div class="skip-controls">
        <button class="skip-btn" id="skipBackBtn">
          <i class="fas fa-step-backward"></i> Skip Back 10s
        </button>
        <button class="skip-btn" id="skipForwardBtn">
          <i class="fas fa-step-forward"></i> Skip Forward 10s
        </button>
      </div>
      
      <!-- Subtitle and audio track controls -->
      <div class="subtitle-controls">
        <span class="control-label">Subtitles:</span>
        <select class="control-select" id="subtitleSelect">
          <option value="none">None</option>
          <option value="english">English</option>
          <option value="spanish">Spanish</option>
          <option value="french">French</option>
        </select>
      </div>
      
      <div class="audio-controls">
        <span class="control-label">Audio Track:</span>
        <select class="control-select" id="audioTrackSelect">
          <option value="default">Default</option>
          <option value="english">English</option>
          <option value="spanish">Spanish</option>
          <option value="french">French</option>
        </select>
      </div>
      
      <div class="controls">
        <a id="openBtn" target="_blank" class="btn">
          <i class="fas fa-external-link-alt"></i>Open Original
        </a>
        <a id="downloadBtn" download class="btn">
          <i class="fas fa-download"></i>Download
        </a>
        <button id="playerOptionsBtn" class="btn">
          <i class="fas fa-play-circle"></i>Open in Player
        </button>
        <a id="newContentBtn" class="btn">
          <i class="fas fa-plus"></i>New Content
        </a>
      </div>
      
      <div class="background-selector">
        <div class="background-label">Change Background:</div>
        <div class="background-options">
          <div class="bg-option active" data-bg="https://images.unsplash.com/photo-1470225620780-dba8ba36b745?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80">
            <img src="https://images.unsplash.com/photo-1470225620780-dba8ba36b745?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80" alt="Concert">
          </div>
          <div class="bg-option" data-bg="https://images.unsplash.com/photo-1514525253161-7a46d19cd819?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1548&q=80">
            <img src="https://images.unsplash.com/photo-1514525253161-7a46d19cd819?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1548&q=80" alt="Music">
          </div>
          <div class="bg-option" data-bg="https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80">
            <img src="https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80" alt="DJ">
          </div>
          <div class="bg-option" data-bg="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80">
            <img src="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80" alt="Headphones">
          </div>
        </div>
      </div>
    </div>
    
    <footer>
      <p>GlassTech Media Player &copy; 2025 | Immersive High-Tech Experience</p>
    </footer>
  </div>

  <!-- Player Options Modal -->
  <div id="playerModal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h2 class="modal-title">Open With External Player</h2>
        <button class="close-modal">&times;</button>
      </div>
      <p>Select your preferred media player to open this content:</p>
      
      <div class="player-options">
        <div class="player-option" data-player="vlc">
          <div class="player-icon">
            <i class="fas fa-play-circle"></i>
          </div>
          <div class="player-name">VLC Player</div>
        </div>
        
        <div class="player-option" data-player="mx">
          <div class="player-icon">
            <i class="fas fa-play-circle"></i>
          </div>
          <div class="player-name">MX Player</div>
        </div>
        
        <div class="player-option" data-player="browser">
          <div class="player-icon">
            <i class="fas fa-window-restore"></i>
          </div>
          <div class="player-name">Browser Player</div>
        </div>
        
        <div class="player-option" data-player="download">
          <div class="player-icon">
            <i class="fas fa-download"></i>
          </div>
          <div class="player-name">Download</div>
        </div>
      </div>
      
      <div class="download-info">
        <p><strong>Note:</strong> For external players to work, you need to have the app installed on your device.</p>
      </div>
    </div>
  </div>

  <script>
    let mediaUrl = '';
    let mediaType = '';
    let mediaElement = null;
    let mediaCategory = '';
    let backgroundInterval;
    let subtitleDisplay = null;
    let currentSubtitle = 'none';
    
    // Enhanced background images for different media categories
    const backgroundImages = {
      movie: [
        'https://images.unsplash.com/photo-1489599809519-364a47ae3cde?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1536440136628-849c177e76a1?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1595769816263-9b910be24d5f?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1574267432553-4b4628081c31?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1517604931442-7e0c8ed2963c?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80'
      ],
      webseries: [
        'https://images.unsplash.com/photo-1616530940355-351fabd9526b?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1592417817098-8fd3d9eb14a5?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1585951237318-9ea5e175b891?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80'
      ],
      anime: [
        'https://images.unsplash.com/photo-1633617477271-d4f351ff7c7c?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1578662996442-48f60103fc96?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1579546929662-711aa81148cf?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1620641788421-7a1c342ea42e?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1542831371-29b0f74f9713?ixlib=rb-4.0.3&auto=format&fit=crop&w=1740&q=80'
      ],
      default: [
        'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1548&q=80',
        'https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80',
        'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1740&q=80'
      ]
    };
    
    // Sample subtitles for demonstration
    const subtitles = {
      none: [],
      english: [
        { start: 5, end: 10, text: "Welcome to GlassTech Media Player" },
        { start: 15, end: 20, text: "Enjoy your media experience" },
        { start: 25, end: 30, text: "High-quality playback with advanced controls" }
      ],
      spanish: [
        { start: 5, end: 10, text: "Bienvenido a GlassTech Media Player" },
        { start: 15, end: 20, text: "Disfruta de tu experiencia multimedia" },
        { start: 25, end: 30, text: "Reproducción de alta calidad con controles avanzados" }
      ],
      french: [
        { start: 5, end: 10, text: "Bienvenue sur GlassTech Media Player" },
        { start: 15, end: 20, text: "Profitez de votre expérience multimédia" },
        { start: 25, end: 30, text: "Lecture haute qualité avec commandes avancées" }
      ]
    };
    
    // Initialize the player with a sample media
    function initPlayer() {
      // Set a sample media URL for demonstration
      mediaUrl = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4';
      mediaType = 'video';
      mediaCategory = 'movie';
      
      // Update UI
      updateMediaInfo();
      createMediaPlayer();
      startBackgroundRotation();
      createParticles();
      setupEventListeners();
      
      // Create subtitle display element
      subtitleDisplay = document.createElement('div');
      subtitleDisplay.className = 'subtitle-display';
      subtitleDisplay.style.opacity = '0';
      document.querySelector('.media-display').appendChild(subtitleDisplay);
    }
    
    // Update media information display
    function updateMediaInfo() {
      document.querySelector('.media-url').textContent = 'Content from secure source';
      document.querySelector('.media-type').textContent = mediaType.charAt(0).toUpperCase() + mediaType.slice(1);
      document.querySelector('.media-category').textContent = mediaCategory.charAt(0).toUpperCase() + mediaCategory.slice(1);
      
      // Update download and open buttons
      document.getElementById('downloadBtn').href = mediaUrl;
      document.getElementById('openBtn').href = mediaUrl;
    }
    
    // Create the appropriate media player
    function createMediaPlayer() {
      const playerElement = document.getElementById('player');
      playerElement.innerHTML = '';
      
      if (mediaType === 'video') {
        // Create video element
        const video = document.createElement('video');
        video.src = mediaUrl;
        video.controls = false;
        video.autoplay = true;
        video.muted = true; // Start muted for autoplay
        video.className = 'media-content';
        
        // Create custom controls
        const controls = document.createElement('div');
        controls.className = 'custom-video-controls';
        controls.innerHTML = `
          <button class="control-btn" id="playPauseBtn">
            <i class="fas fa-play"></i>
          </button>
          <div class="progress-container">
            <div class="progress-bar" id="progressBar"></div>
          </div>
          <button class="control-btn" id="muteBtn">
            <i class="fas fa-volume-up"></i>
          </button>
          <button class="control-btn" id="fullscreenBtn">
            <i class="fas fa-expand"></i>
          </button>
        `;
        
        playerElement.appendChild(video);
        playerElement.appendChild(controls);
        mediaElement = video;
        
        // Setup video controls
        setupVideoControls(video, controls);
      } else if (mediaType === 'audio') {
        // Create audio element
        const audio = document.createElement('audio');
        audio.src = mediaUrl;
        audio.controls = false;
        audio.autoplay = true;
        audio.muted = true; // Start muted for autoplay
        
        // Create custom audio player
        const audioPlayer = document.createElement('div');
        audioPlayer.className = 'custom-audio-player';
        audioPlayer.innerHTML = `
          <button class="control-btn" id="audioPlayPauseBtn">
            <i class="fas fa-play"></i>
          </button>
          <div class="progress-container">
            <div class="progress-bar" id="audioProgressBar"></div>
          </div>
          <button class="control-btn" id="audioMuteBtn">
            <i class="fas fa-volume-up"></i>
          </button>
          <span id="audioTime">0:00 / 0:00</span>
        `;
        
        playerElement.appendChild(audioPlayer);
        mediaElement = audio;
        
        // Setup audio controls
        setupAudioControls(audio, audioPlayer);
      } else {
        // For images or other content
        const img = document.createElement('img');
        img.src = mediaUrl;
        img.alt = 'Media content';
        playerElement.appendChild(img);
        mediaElement = img;
      }
    }
    
    // Setup video controls functionality
    function setupVideoControls(video, controls) {
      const playPauseBtn = controls.querySelector('#playPauseBtn');
      const progressBar = controls.querySelector('#progressBar');
      const progressContainer = controls.querySelector('.progress-container');
      const muteBtn = controls.querySelector('#muteBtn');
      const fullscreenBtn = controls.querySelector('#fullscreenBtn');
      
      // Play/Pause functionality
      playPauseBtn.addEventListener('click', () => {
        if (video.paused) {
          video.play();
          playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
        } else {
          video.pause();
          playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        }
      });
      
      // Update progress bar
      video.addEventListener('timeupdate', () => {
        const progress = (video.currentTime / video.duration) * 100;
        progressBar.style.width = `${progress}%`;
        
        // Update subtitles
        updateSubtitles(video.currentTime);
      });
      
      // Seek functionality
      progressContainer.addEventListener('click', (e) => {
        const pos = (e.pageX - progressContainer.getBoundingClientRect().left) / progressContainer.offsetWidth;
        video.currentTime = pos * video.duration;
      });
      
      // Mute functionality
      muteBtn.addEventListener('click', () => {
        video.muted = !video.muted;
        muteBtn.innerHTML = video.muted ? 
          '<i class="fas fa-volume-mute"></i>' : 
          '<i class="fas fa-volume-up"></i>';
      });
      
      // Fullscreen functionality
      fullscreenBtn.addEventListener('click', () => {
        if (!document.fullscreenElement) {
          if (video.requestFullscreen) {
            video.requestFullscreen();
          } else if (video.webkitRequestFullscreen) {
            video.webkitRequestFullscreen();
          } else if (video.msRequestFullscreen) {
            video.msRequestFullscreen();
          }
        } else {
          if (document.exitFullscreen) {
            document.exitFullscreen();
          }
        }
      });
      
      // Update play/pause button based on video state
      video.addEventListener('play', () => {
        playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
      });
      
      video.addEventListener('pause', () => {
        playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
      });
    }
    
    // Setup audio controls functionality
    function setupAudioControls(audio, audioPlayer) {
      const playPauseBtn = audioPlayer.querySelector('#audioPlayPauseBtn');
      const progressBar = audioPlayer.querySelector('#audioProgressBar');
      const progressContainer = audioPlayer.querySelector('.progress-container');
      const muteBtn = audioPlayer.querySelector('#audioMuteBtn');
      const timeDisplay = audioPlayer.querySelector('#audioTime');
      
      // Play/Pause functionality
      playPauseBtn.addEventListener('click', () => {
        if (audio.paused) {
          audio.play();
          playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
        } else {
          audio.pause();
          playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        }
      });
      
      // Update progress bar and time
      audio.addEventListener('timeupdate', () => {
        const progress = (audio.currentTime / audio.duration) * 100;
        progressBar.style.width = `${progress}%`;
        
        // Format time display
        const currentTime = formatTime(audio.currentTime);
        const duration = formatTime(audio.duration);
        timeDisplay.textContent = `${currentTime} / ${duration}`;
        
        // Update subtitles
        updateSubtitles(audio.currentTime);
      });
      
      // Seek functionality
      progressContainer.addEventListener('click', (e) => {
        const pos = (e.pageX - progressContainer.getBoundingClientRect().left) / progressContainer.offsetWidth;
        audio.currentTime = pos * audio.duration;
      });
      
      // Mute functionality
      muteBtn.addEventListener('click', () => {
        audio.muted = !audio.muted;
        muteBtn.innerHTML = audio.muted ? 
          '<i class="fas fa-volume-mute"></i>' : 
          '<i class="fas fa-volume-up"></i>';
      });
      
      // Update play/pause button based on audio state
      audio.addEventListener('play', () => {
        playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
      });
      
      audio.addEventListener('pause', () => {
        playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
      });
    }
    
    // Format time in minutes:seconds
    function formatTime(seconds) {
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins}:${secs < 10 ? '0' : ''}${secs}`;
    }
    
    // Setup event listeners for UI elements
    function setupEventListeners() {
      // Background selector
      document.querySelectorAll('.bg-option').forEach(option => {
        option.addEventListener('click', function() {
          document.querySelectorAll('.bg-option').forEach(opt => opt.classList.remove('active'));
          this.classList.add('active');
          
          const bgUrl = this.getAttribute('data-bg');
          document.body.style.backgroundImage = `linear-gradient(135deg, 
            rgba(26, 42, 108, 0.15), 
            rgba(42, 58, 124, 0.15), 
            rgba(58, 74, 140, 0.15)), 
            url('${bgUrl}')`;
        });
      });
      
      // Player options modal
      const modal = document.getElementById('playerModal');
      const openModalBtn = document.getElementById('playerOptionsBtn');
      const closeModalBtn = document.querySelector('.close-modal');
      
      openModalBtn.addEventListener('click', () => {
        modal.style.display = 'flex';
      });
      
      closeModalBtn.addEventListener('click', () => {
        modal.style.display = 'none';
      });
      
      window.addEventListener('click', (e) => {
        if (e.target === modal) {
          modal.style.display = 'none';
        }
      });
      
      // Player options
      document.querySelectorAll('.player-option').forEach(option => {
        option.addEventListener('click', function() {
          const player = this.getAttribute('data-player');
          alert(`Opening with ${player.toUpperCase()} player...`);
          modal.style.display = 'none';
        });
      });
      
      // New content button
      document.getElementById('newContentBtn').addEventListener('click', () => {
        // In a real app, this would open a file picker or URL input
        alert('New content feature would open a file picker or URL input');
      });
      
      // Skip buttons
      document.getElementById('skipBackBtn').addEventListener('click', () => {
        if (mediaElement && (mediaElement.tagName === 'VIDEO' || mediaElement.tagName === 'AUDIO')) {
          mediaElement.currentTime = Math.max(0, mediaElement.currentTime - 10);
        }
      });
      
      document.getElementById('skipForwardBtn').addEventListener('click', () => {
        if (mediaElement && (mediaElement.tagName === 'VIDEO' || mediaElement.tagName === 'AUDIO')) {
          mediaElement.currentTime = Math.min(mediaElement.duration, mediaElement.currentTime + 10);
        }
      });
      
      // Subtitle selection
      document.getElementById('subtitleSelect').addEventListener('change', function() {
        currentSubtitle = this.value;
        subtitleDisplay.style.opacity = '0';
      });
      
      // Audio track selection
      document.getElementById('audioTrackSelect').addEventListener('change', function() {
        alert(`Switching to ${this.value} audio track`);
      });
    }
    
    // Update subtitles based on current time
    function updateSubtitles(currentTime) {
      if (!subtitleDisplay) return;
      
      const currentSubs = subtitles[currentSubtitle];
      let currentSubtitleText = '';
      
      for (const sub of currentSubs) {
        if (currentTime >= sub.start && currentTime <= sub.end) {
          currentSubtitleText = sub.text;
          break;
        }
      }
      
      if (currentSubtitleText) {
        subtitleDisplay.textContent = currentSubtitleText;
        subtitleDisplay.style.opacity = '1';
      } else {
        subtitleDisplay.style.opacity = '0';
      }
    }
    
    // Create floating particles for visual effect
    function createParticles() {
      const particlesContainer = document.getElementById('particles');
      const particleCount = 50;
      
      for (let i = 0; i < particleCount; i++) {
        const particle = document.createElement('div');
        particle.className = 'particle';
        
        // Random position and size
        const size = Math.random() * 3 + 1;
        particle.style.width = `${size}px`;
        particle.style.height = `${size}px`;
        particle.style.left = `${Math.random() * 100}%`;
        
        // Random animation delay and duration
        const delay = Math.random() * 15;
        const duration = 15 + Math.random() * 10;
        particle.style.animationDelay = `${delay}s`;
        particle.style.animationDuration = `${duration}s`;
        
        particlesContainer.appendChild(particle);
      }
    }
    
    // Start rotating background images based on media category
    function startBackgroundRotation() {
      const category = mediaCategory in backgroundImages ? mediaCategory : 'default';
      const images = backgroundImages[category];
      let currentIndex = 0;
      
      // Clear any existing interval
      if (backgroundInterval) {
        clearInterval(backgroundInterval);
      }
      
      // Set initial background
      document.body.style.backgroundImage = `linear-gradient(135deg, 
        rgba(26, 42, 108, 0.15), 
        rgba(42, 58, 124, 0.15), 
        rgba(58, 74, 140, 0.15)), 
        url('${images[currentIndex]}')`;
      
      // Rotate background every 10 seconds
      backgroundInterval = setInterval(() => {
        currentIndex = (currentIndex + 1) % images.length;
        document.body.style.backgroundImage = `linear-gradient(135deg, 
          rgba(26, 42, 108, 0.15), 
          rgba(42, 58, 124, 0.15), 
          rgba(58, 74, 140, 0.15)), 
          url('${images[currentIndex]}')`;
      }, 10000);
    }
    
    // Initialize the player when the page loads
    window.addEventListener('DOMContentLoaded', initPlayer);
  </script>
</body>
</html>
