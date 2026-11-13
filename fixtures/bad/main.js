import * as THREE from 'three';
const renderer = new THREE.WebGLRenderer();
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
camera.position.z = 3;
const cube = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshBasicMaterial({ color: 0xff0000 }));
scene.add(cube);
window.app = { scene, camera, renderer, controls: null, presets: {} };
function loop() { requestAnimationFrame(loop); renderer.render(scene, camera); }
loop();
