import * as THREE from 'three';
import { OrbitControls } from './vendor/OrbitControls.js';
import { OBJLoader } from './vendor/OBJLoader.js';
import { MTLLoader } from './vendor/MTLLoader.js';
const container=document.getElementById('viewer');
const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));container.append(renderer.domElement);
const scene=new THREE.Scene();
const camera=new THREE.PerspectiveCamera(40,1,.01,1000);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;
scene.add(new THREE.HemisphereLight(0xffffff,0xb9bbaa,2));
const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(4,6,5);scene.add(light);
let model=null;
function fit(){if(!model)return;const box=new THREE.Box3().setFromObject(model);const size=box.getSize(new THREE.Vector3());const center=box.getCenter(new THREE.Vector3());const radius=Math.max(size.x,size.y,size.z)||1;controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(0,radius*.15,radius*2.2/Math.min(camera.aspect,1)));camera.near=radius/1000;camera.far=radius*100;camera.updateProjectionMatrix();controls.update();}
new ResizeObserver(()=>{const w=container.clientWidth,h=container.clientHeight;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}).observe(container);
renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});
document.getElementById('reset-view').onclick=fit;
document.getElementById('rotate-model').onclick=()=>{if(model){model.rotation.x+=Math.PI/2;fit();}};
export function clearModel(){if(model){scene.remove(model);model.traverse(obj=>{obj.geometry?.dispose();if(obj.material)for(const mat of [].concat(obj.material)){mat.map?.dispose();mat.dispose();}});model=null;}document.getElementById('empty').hidden=false;document.getElementById('reset-view').disabled=true;document.getElementById('rotate-model').disabled=true;}
export async function loadModel(base){
  clearModel();
  const response=await fetch(base+'head.obj');if(!response.ok)throw new Error('OBJ file is missing');
  const text=await response.text();const materialFile=text.match(/^mtllib\s+(.+)$/m)?.[1]?.trim();
  const loader=new OBJLoader();
  if(materialFile){const materials=await new MTLLoader().setPath(base).loadAsync(materialFile);materials.preload();loader.setMaterials(materials);}
  model=loader.parse(text);model.traverse(obj=>{if(obj.isMesh){if(!materialFile)obj.material=new THREE.MeshStandardMaterial({color:0xb8c5b1,roughness:.85});for(const material of [].concat(obj.material))material.side=THREE.DoubleSide;}});
  scene.add(model);fit();document.getElementById('empty').hidden=true;
  document.getElementById('reset-view').disabled=false;document.getElementById('rotate-model').disabled=false;
}
