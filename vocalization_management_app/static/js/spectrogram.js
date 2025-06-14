/**
 * Basic Spectrogram Visualization
 * A simplified, robust implementation for visualizing audio spectrograms
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize the spectrogram
    initializeSpectrogram();
});

function initializeSpectrogram() {
    // Get DOM elements
    const audioPlayer = document.getElementById('audioPlayer');
    const playPauseBtn = document.getElementById('playPauseBtn');
    const timeDisplay = document.getElementById('timeDisplay');
    const timelineContainer = document.getElementById('timelineContainer');
    const playhead = document.getElementById('playhead');
    const basicSpectrogram = document.getElementById('basicSpectrogram');
    const spectrogramStatus = document.getElementById('spectrogramStatus');
    const spectrogramColorBtn = document.getElementById('spectrogramColorBtn');
    const spectrogramSensitivityUpBtn = document.getElementById('spectrogramSensitivityUpBtn');
    const spectrogramSensitivityDownBtn = document.getElementById('spectrogramSensitivityDownBtn');
    
    // Skip if essential elements don't exist
    if (!audioPlayer || !basicSpectrogram) {
        console.log('Essential elements for spectrogram not found');
        return;
    }
    
    // Update status
    if (spectrogramStatus) {
        spectrogramStatus.textContent = 'Initializing...';
        spectrogramStatus.className = 'badge bg-info';
    }
    
    // Initialize variables
    let spectrogramCtx = null;
    let audioContext = null;
    let analyser = null;
    let dataArray = null;
    let sensitivity = 1.5;
    let colorMode = 'grayscale'; // Set grayscale as default
    let animationFrameId = null;
    let spectrogramInitialized = false;
    
    // Color schemes - removed rainbow, kept only grayscale and heatmap
    const colorSchemes = {
        heatmap: ['#000080', '#0000ff', '#00ffff', '#ffff00', '#ff0000'],
        grayscale: ['#000000', '#333333', '#666666', '#999999', '#ffffff']
    };
    
    // Initialize the canvas
    function initCanvas() {
        try {
            // Set canvas dimensions
            basicSpectrogram.width = basicSpectrogram.offsetWidth || 800;
            basicSpectrogram.height = basicSpectrogram.offsetHeight || 400;
            
            // Get the 2D context
            spectrogramCtx = basicSpectrogram.getContext('2d', { alpha: false });
            
            if (!spectrogramCtx) {
                throw new Error('Could not get canvas context');
            }
            
            // Draw initial visualization
            drawInitialVisualization();
            
            return true;
        } catch (e) {
            console.error('Error initializing canvas:', e);
            if (spectrogramStatus) {
                spectrogramStatus.textContent = 'Canvas Error';
                spectrogramStatus.className = 'badge bg-danger';
            }
            return false;
        }
    }
    
    // Draw initial visualization
    function drawInitialVisualization() {
        if (!spectrogramCtx) return;
        
        // Clear canvas with gradient background
        const gradient = spectrogramCtx.createLinearGradient(0, 0, 0, basicSpectrogram.height);
        gradient.addColorStop(0, '#000033');
        gradient.addColorStop(1, '#000011');
        spectrogramCtx.fillStyle = gradient;
        spectrogramCtx.fillRect(0, 0, basicSpectrogram.width, basicSpectrogram.height);
        
        // Draw frequency labels
        drawFrequencyLabels();
        
        // Draw welcome message
        spectrogramCtx.fillStyle = 'white';
        spectrogramCtx.font = 'bold 16px Arial';
        spectrogramCtx.textAlign = 'center';
        spectrogramCtx.fillText('Click Play to Start Live Spectrogram', 
                              basicSpectrogram.width / 2, 
                              basicSpectrogram.height / 2 - 20);
        
        // Draw instructions
        spectrogramCtx.font = '12px Arial';
        spectrogramCtx.fillText('Frequencies will be displayed from 0-10,000 Hz', 
                              basicSpectrogram.width / 2, 
                              basicSpectrogram.height / 2 + 10);
        spectrogramCtx.fillText('Saw calls will be marked with red vertical lines', 
                              basicSpectrogram.width / 2, 
                              basicSpectrogram.height / 2 + 30);
        
        // Draw color test pattern
        drawColorTestPattern();
    }
    
    // Draw frequency labels
    function drawFrequencyLabels() {
        if (!spectrogramCtx) return;
        
        // Draw frequency scale on the left
        spectrogramCtx.fillStyle = 'rgba(0, 0, 40, 0.7)';
        spectrogramCtx.fillRect(0, 0, 50, basicSpectrogram.height);
        
        const freqLabels = [0, 2500, 5000, 7500, 10000]; // Hz
        spectrogramCtx.fillStyle = 'white';
        spectrogramCtx.font = '10px Arial';
        spectrogramCtx.textAlign = 'left';
        
        freqLabels.forEach(freq => {
            // Position labels from bottom (0Hz) to top (10kHz)
            const y = basicSpectrogram.height - (freq / 10000) * basicSpectrogram.height;
            spectrogramCtx.fillText(`${freq} Hz`, 5, y);
            
            // Draw horizontal grid line
            spectrogramCtx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
            spectrogramCtx.beginPath();
            spectrogramCtx.moveTo(50, y);
            spectrogramCtx.lineTo(basicSpectrogram.width, y);
            spectrogramCtx.stroke();
        });
    }
    
    // Draw color test pattern
    function drawColorTestPattern() {
        if (!spectrogramCtx) return;
        
        // Draw color bars at the bottom
        const barHeight = 20;
        const barWidth = (basicSpectrogram.width - 50) / 5;
        const colors = ['red', 'orange', 'yellow', 'green', 'blue'];
        
        // Draw the bars
        for (let i = 0; i < colors.length; i++) {
            spectrogramCtx.fillStyle = colors[i];
            spectrogramCtx.fillRect(
                50 + i * barWidth, 
                basicSpectrogram.height - barHeight, 
                barWidth, 
                barHeight
            );
        }
        
        // Add label
        spectrogramCtx.fillStyle = 'white';
        spectrogramCtx.textAlign = 'center';
        spectrogramCtx.font = '10px Arial';
        spectrogramCtx.fillText(
            'Color Test Pattern', 
            basicSpectrogram.width / 2, 
            basicSpectrogram.height - 5
        );
    }
    
    // Initialize Web Audio API
    function initAudio() {
        try {
            // Create audio context
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            
            // Create media element source
            const source = audioContext.createMediaElementSource(audioPlayer);
            
            // Create analyzer
            analyser = audioContext.createAnalyser();
            analyser.fftSize = 1024; // Must be a power of 2
            analyser.smoothingTimeConstant = 0.8;
            
            // Connect nodes
            source.connect(analyser);
            analyser.connect(audioContext.destination);
            
            // Create data array for frequency data
            dataArray = new Uint8Array(analyser.frequencyBinCount);
            
            // Start visualization
            startVisualization();
            
            // Update status and hide loading indicator
            if (spectrogramStatus) {
                spectrogramStatus.textContent = 'Running';
                spectrogramStatus.className = 'badge bg-success';
            }
            
            // Hide the loading indicator
            const loadingIndicator = document.querySelector('.loading-indicator');
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            
            return true;
        } catch (e) {
            console.error('Error initializing audio:', e);
            if (spectrogramStatus) {
                spectrogramStatus.textContent = 'Audio Error';
                spectrogramStatus.className = 'badge bg-danger';
            }
            
            // Hide the loading indicator even on error
            const loadingIndicator = document.querySelector('.loading-indicator');
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            
            return false;
        }
    }
    
    // Start visualization loop
    function startVisualization() {
        // Cancel any existing animation frame
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
        }
        
        // Start the visualization loop
        visualize();
    }
    
    // Main visualization function
    function visualize() {
        if (!analyser || !spectrogramCtx || !dataArray) {
            // If not ready, try again later
            animationFrameId = requestAnimationFrame(visualize);
            return;
        }
        
        // Hide the loading indicator when visualization starts running
        const loadingIndicator = document.querySelector('.loading-indicator');
        if (loadingIndicator && loadingIndicator.style.display !== 'none') {
            loadingIndicator.style.display = 'none';
            console.log('Visualization started, hiding loading indicator');
        }
        
        // Get frequency data
        analyser.getByteFrequencyData(dataArray);
        
        // Shift existing spectrogram to the left
        spectrogramCtx.drawImage(
            basicSpectrogram, 
            51, 0, basicSpectrogram.width - 51, basicSpectrogram.height, 
            50, 0, basicSpectrogram.width - 51, basicSpectrogram.height
        );
        
        // Draw new column on the right
        const columnWidth = 1;
        const columnX = basicSpectrogram.width - columnWidth;
        
        // Clear the area for the new column
        spectrogramCtx.fillStyle = 'black';
        spectrogramCtx.fillRect(columnX, 0, columnWidth, basicSpectrogram.height);
        
        // Draw the new frequency data
        for (let i = 0; i < dataArray.length; i++) {
            // Calculate the y position (0 is at the top, so we invert)
            const percent = i / dataArray.length;
            const y = basicSpectrogram.height - (percent * basicSpectrogram.height);
            
            // Get the value and apply sensitivity
            const value = dataArray[i] / 255.0 * sensitivity;
            
            // Get color based on value and color mode
            const color = getColor(value);
            
            // Draw a pixel
            spectrogramCtx.fillStyle = color;
            spectrogramCtx.fillRect(columnX, y, columnWidth, 1);
        }
        
        // Redraw frequency labels
        drawFrequencyLabels();
        
        // Continue the loop
        animationFrameId = requestAnimationFrame(visualize);
    }
    
    // Get color based on value and color mode
    function getColor(value) {
        // Clamp value between 0 and 1
        value = Math.min(1, Math.max(0, value));
        
        if (colorMode === 'grayscale') {
            // Grayscale - simple black to white gradient
            const intensity = Math.floor(value * 255);
            return `rgb(${intensity}, ${intensity}, ${intensity})`;
        } else { // heatmap is the only other option now
            // Blue to red heatmap
            const r = Math.floor(value * 255);
            const g = Math.floor((1 - Math.abs(value - 0.5) * 2) * 255);
            const b = Math.floor((1 - value) * 255);
            return `rgb(${r}, ${g}, ${b})`;
        }
    }
    
    // Set up event listeners
    function setupEventListeners() {
        // Play/Pause button
        if (playPauseBtn) {
            playPauseBtn.addEventListener('click', function() {
                if (audioPlayer.paused) {
                    // Initialize audio on first play
                    if (!audioContext) {
                        initAudio();
                    }
                    audioPlayer.play();
                    playPauseBtn.innerHTML = '<i class="fas fa-pause"></i>';
                } else {
                    audioPlayer.pause();
                    playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
                }
            });
        }
        
        // Color mode button - toggle between grayscale and heatmap only
        if (spectrogramColorBtn) {
            spectrogramColorBtn.addEventListener('click', function() {
                // Toggle between grayscale and heatmap
                colorMode = (colorMode === 'grayscale') ? 'heatmap' : 'grayscale';
                console.log('Color mode changed to:', colorMode);
                
                // Update button text to show current mode
                spectrogramColorBtn.title = `Switch to ${colorMode === 'grayscale' ? 'heatmap' : 'grayscale'} mode`;
                
                // Optional: Add visual indication of current mode
                if (colorMode === 'grayscale') {
                    spectrogramColorBtn.innerHTML = '<i class="fas fa-adjust"></i>';
                } else {
                    spectrogramColorBtn.innerHTML = '<i class="fas fa-fire"></i>';
                }
            });
        }
        
        // Sensitivity buttons
        if (spectrogramSensitivityUpBtn) {
            spectrogramSensitivityUpBtn.addEventListener('click', function() {
                sensitivity = Math.min(5.0, sensitivity + 0.5);
                console.log('Sensitivity increased to:', sensitivity);
            });
        }
        
        if (spectrogramSensitivityDownBtn) {
            spectrogramSensitivityDownBtn.addEventListener('click', function() {
                sensitivity = Math.max(0.5, sensitivity - 0.5);
                console.log('Sensitivity decreased to:', sensitivity);
            });
        }
        
        // Time update for playhead
        if (audioPlayer && playhead) {
            audioPlayer.addEventListener('timeupdate', function() {
                if (timelineContainer) {
                    const containerWidth = timelineContainer.clientWidth;
                    const position = (audioPlayer.currentTime / audioPlayer.duration) * containerWidth;
                    playhead.style.left = position + 'px';
                }
                
                // Update time display
                if (timeDisplay) {
                    const currentTime = formatTime(audioPlayer.currentTime);
                    const duration = formatTime(audioPlayer.duration);
                    timeDisplay.textContent = `${currentTime} / ${duration}`;
                }
            });
        }
    }
    
    // Format time in HH:MM:SS
    function formatTime(seconds) {
        if (isNaN(seconds)) return '00:00:00';
        
        const hrs = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
    
    // Initialize everything
    if (initCanvas()) {
        setupEventListeners();
        if (spectrogramStatus) {
            spectrogramStatus.textContent = 'Ready';
            spectrogramStatus.className = 'badge bg-success';
        }
        console.log('Spectrogram initialized successfully');
    }
}
