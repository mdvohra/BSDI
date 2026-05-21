// import React, { useRef, useEffect, useState } from "react";
// import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
// import { MapContainer, TileLayer } from "react-leaflet";
// import GeoTIFFMap from "./GeoTIFFMap";
// import SuperResolutionMap from "./SuperResolutionMap";  // NEW IMPORT


// const SRImageOnlyViewer = ({ src }) => {
//   if (!src) {
//     return (
//       <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#6B7280" }}>
//         No SR output image available.
//       </div>
//     );
//   }

//   return (
//     <div style={{ height: "100%", width: "100%", background: "#0b0f19" }}>
//       <TransformWrapper
//         initialScale={1}
//         minScale={0.5}
//         maxScale={6}
//         wheel={{ step: 0.2 }}
//         doubleClick={{ step: 1 }}
//         panning={{ velocityDisabled: true }}
//       >
//         {({ zoomIn, zoomOut, resetTransform }) => (
//           <>
//             <div style={{ display: "flex", justifyContent: "center", gap: "10px", padding: "10px" }}>
//               <button onClick={zoomIn}>+</button>
//               <button onClick={zoomOut}>-</button>
//               <button onClick={resetTransform}>Reset</button>
//             </div>

//             <TransformComponent wrapperStyle={{ width: "100%", height: "calc(100% - 52px)" }}>
//               <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
//                 <img
//                   src={src}
//                   alt="Super-resolved output"
//                   style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
//                 />
//               </div>
//             </TransformComponent>
//           </>
//         )}
//       </TransformWrapper>
//     </div>
//   );
// };

// const ImageViewer = ({ imageData, fileType, file, detectionData, imageMetadata, overlayImage }) => {
//   const canvasRef = useRef(null);
//   const [leftReady, setLeftReady] = useState(false);
//   const [rightReady, setRightReady] = useState(false);
//   const [compositeImage, setCompositeImage] = useState(null);

//   const leftMapRef = useRef(null);
//   const rightMapRef = useRef(null);
//   const isSyncingRef = useRef(false);

  

//   console.log("ImageViewer props:", {
//     imageData: !!imageData,
//     detectionData: !!detectionData,
//     imageMetadata: !!imageMetadata,
//     overlayImage: !!overlayImage,
//     fileType,
//     file: file?.type
//   });

//   // Create composite image with overlay for regular images (non-TIFF)
//   useEffect(() => {
//     if (!imageData || !overlayImage || file?.type === "image/tiff") {
//       console.log("Skipping composite:", {
//         imageData: !!imageData,
//         overlayImage: !!overlayImage,
//         isTiff: file?.type === "image/tiff"
//       });
//       return;
//     }

//     console.log("Creating composite image...");
//     const canvas = canvasRef.current;
//     if (!canvas) {
//       console.error("Canvas ref not available");
//       return;
//     }

//     const ctx = canvas.getContext("2d");
//     const baseImg = new Image();
//     const overlayImg = new Image();

//     baseImg.crossOrigin = "anonymous";
//     overlayImg.crossOrigin = "anonymous";

//     let baseLoaded = false;
//     let overlayLoaded = false;

//     const drawComposite = () => {
//       if (!baseLoaded || !overlayLoaded) return;

//       console.log("Both images loaded, drawing composite");
//       canvas.width = baseImg.width;
//       canvas.height = baseImg.height;

//       ctx.clearRect(0, 0, canvas.width, canvas.height);
//       ctx.drawImage(baseImg, 0, 0);
//       ctx.globalAlpha = 0.7;
//       ctx.drawImage(overlayImg, 0, 0, canvas.width, canvas.height);
//       ctx.globalAlpha = 1.0;

//       canvas.toBlob((blob) => {
//         if (blob) {
//           const url = URL.createObjectURL(blob);
//           setCompositeImage(url);
//           console.log("Composite image created successfully");
//         }
//       }, "image/png");
//     };

//     baseImg.onload = () => {
//       console.log("Base image loaded");
//       baseLoaded = true;
//       drawComposite();
//     };

//     overlayImg.onload = () => {
//       console.log("Overlay image loaded");
//       overlayLoaded = true;
//       drawComposite();
//     };

//     baseImg.onerror = (e) => {
//       console.error("Failed to load base image", e);
//     };

//     overlayImg.onerror = (e) => {
//       console.error("Failed to load overlay image", e);
//     };

//     baseImg.src = imageData;
//     overlayImg.src = overlayImage;

//     return () => {
//       if (compositeImage) {
//         URL.revokeObjectURL(compositeImage);
//       }
//     };
//   }, [imageData, overlayImage, file]);

//   if (!imageData) {
//     return (
//       <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "24rem", color: "#6B7280" }}>
//         <MapContainer center={file ? [0, 0] : [28.6, 77.2]} zoom={file ? 2 : 5} style={{ height: "100%", width: "100%" }}>
//           <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="&copy; OpenStreetMap contributors" />
//         </MapContainer>
//       </div>
//     );
//   }

//   const iconStyle = {
//     fontSize: "18px",
//     color: "#3B82F6",
//     cursor: "pointer",
//     transition: "transform 0.2s ease, color 0.2s ease",
//   };

//   const iconHoverStyle = {
//     transform: "scale(1.1)",
//     color: "#2563EB",
//   };

//   // Check if this is super-resolution mode
//   const isSuperResolution = imageMetadata?.scale_factor !== undefined;

//   console.log("🎯 Rendering mode:", isSuperResolution ? "Super-Resolution" : "Detection");

//   useEffect(() => {
//     if (!leftReady || !rightReady) return;
  
//     const left = leftMapRef.current;
//     const right = rightMapRef.current;
//     if (!left || !right) return;
  
//     const syncFromLeft = () => {
//       if (isSyncingRef.current) return;
//       isSyncingRef.current = true;
  
//       right.setView(left.getCenter(), left.getZoom(), { animate: false });
  
//       requestAnimationFrame(() => {
//         isSyncingRef.current = false;
//       });
//     };
  
//     const syncFromRight = () => {
//       if (isSyncingRef.current) return;
//       isSyncingRef.current = true;
  
//       left.setView(right.getCenter(), right.getZoom(), { animate: false });
  
//       requestAnimationFrame(() => {
//         isSyncingRef.current = false;
//       });
//     };
  
//     left.on("move", syncFromLeft);
//     right.on("move", syncFromRight);
  
//     return () => {
//       left.off("move", syncFromLeft);
//       right.off("move", syncFromRight);
//     };
    
//   }, [leftReady, rightReady]);     

//   // Render TIFF with detections on map (DETECTION MODE)
//   if (file && file.type === "image/tiff" && !isSuperResolution) {
//     console.log("📍 Rendering GeoTIFFMap for detection");
//     return (
//       <div style={{ width: "100%", height: "90vh" }}>
//         <GeoTIFFMap 
//           tiffBlob={file} 
//           detectionData={detectionData} 
//           imageMetadata={imageMetadata}
//         />
//       </div>
//     );
//   }

//   // SUPER-RESOLUTION MODE
// if (isSuperResolution && overlayImage && imageMetadata?.bounds) {
//   return (
//     <div style={{ width: "100%", height: "90vh", display: "flex", gap: "10px" }}>
//       {/* Left: same logic as before */}
//       <div style={{ flex: 1, minWidth: 0, borderRadius: "8px", overflow: "hidden" }}>
//         <SuperResolutionMap
//           overlayUrl={null}
//           imageMetadata={imageMetadata}
//           originalTiffBlob={file && file.type === "image/tiff" ? file : null}
//           onMapReady={(map) => {
//             leftMapRef.current = map;
//             setLeftReady(true)
//           }}
//         />
//       </div>

//       <div style={{ flex: 1, minWidth: 0, borderRadius: "8px", overflow: "hidden" }}>
//         <SuperResolutionMap
//           imageMetadata={imageMetadata}
//           originalTiffBlob={null} //  disable raw layer
//           overlayUrl={overlayImage}
//           onMapReady={(map) => {
//             rightMapRef.current = map;
//             setRightReady(true)
//           }}
//         />
//       </div>
//     </div>
//   );
// }

//   // For regular images show composite if available, else overlay, else original
//   const displayImage = compositeImage || overlayImage || imageData;

//   console.log("Displaying image:", {
//     hasComposite: !!compositeImage,
//     hasOverlay: !!overlayImage,
//     hasOriginal: !!imageData,
//     using: compositeImage ? "composite" : overlayImage ? "overlay" : "original"
//   });

//   return (
//     <div className="">
//       {/* Hidden canvas for compositing */}
//       <canvas ref={canvasRef} style={{ display: "none" }} />

//       <TransformWrapper
//         initialScale={1}
//         initialPositionX={0}
//         initialPositionY={0}
//         options={{
//           limitToBounds: true,
//           minScale: 0.5,
//           maxScale: 3,
//           centerContent: true,
//           wheel: { step: 0.2 },
//           doubleClick: { step: 1 },
//           panning: { velocityDisabled: true },
//           zoomIn: { animation: true, animationTime: 500 },
//           zoomOut: { animation: true, animationTime: 500 },
//           reset: { animation: true, animationTime: 500 },
//         }}
//       >
//         {({ zoomIn, zoomOut, resetTransform }) => (
//           <div>
//             <div style={{ display: "flex", justifyContent: "center", marginBottom: "0.1rem", gap: "1rem" }}>
//               <i
//                 onClick={zoomIn}
//                 className="fi fi-rr-zoom-in"
//                 style={iconStyle}
//                 onMouseEnter={(e) => (e.target.style.transform = iconHoverStyle.transform)}
//                 onMouseLeave={(e) => (e.target.style.transform = "scale(1)")}
//               ></i>
//               <i
//                 onClick={zoomOut}
//                 className="fi fi-rr-zoom-out"
//                 style={iconStyle}
//                 onMouseEnter={(e) => (e.target.style.transform = iconHoverStyle.transform)}
//                 onMouseLeave={(e) => (e.target.style.transform = "scale(1)")}
//               ></i>
//               <i
//                 onClick={resetTransform}
//                 className="fi fi-rr-rotate-right"
//                 style={iconStyle}
//                 onMouseEnter={(e) => (e.target.style.transform = iconHoverStyle.transform)}
//                 onMouseLeave={(e) => (e.target.style.transform = "scale(1)")}
//               ></i>
//             </div>

//             {overlayImage && (
//               <div style={{ textAlign: "center", marginBottom: "0.5rem", fontSize: "14px", color: "#10b981", fontWeight: 600 }}>
//                 ✅ Detections overlay {compositeImage ? "composited" : "applied"}
//               </div>
//             )}

//             <div style={{ display: "flex", justifyContent: "center" }}>
//               <TransformComponent>
//                 <img style={{ maxHeight: "80vh" }} src={displayImage} alt="Satellite" loading="lazy" />
//               </TransformComponent>
//             </div>
//           </div>
//         )}
//       </TransformWrapper>
//     </div>
//   );
// };

// export default ImageViewer;



//   // Render super-resolution overlay on map (SUPER-RESOLUTION MODE)
//   // if (isSuperResolution && overlayImage && imageMetadata?.bounds) {
//   //   console.log("🎨 Rendering SuperResolutionMap");
//   //   return (
//   //     <div style={{ width: "100%", height: "90vh" }}>
//   //       <SuperResolutionMap 
//   //         overlayUrl={overlayImage}
//   //         imageMetadata={imageMetadata}
//   //         originalTiffBlob={file && file.type === "image/tiff" ? file : null}
//   //       />
//   //     </div>
//   //   );
//   // }


////////////////////////// NEW LOGIC /////////////////////////////

// import React, { useRef, useEffect, useState } from "react";
// import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
// import { MapContainer, TileLayer } from "react-leaflet";
// import GeoTIFFMap from "./GeoTIFFMap";
// import SuperResolutionMap from "./SuperResolutionMap";

// const SRImageOnlyViewer = ({ src }) => {
//   if (!src) {
//     return (
//       <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#6B7280" }}>
//         No SR output image available.
//       </div>
//     );
//   }

//   return (
//     <div style={{ height: "100%", width: "100%", background: "#0b0f19" }}>
//       <TransformWrapper initialScale={1} minScale={0.5} maxScale={6} wheel={{ step: 0.2 }} doubleClick={{ step: 1 }} panning={{ velocityDisabled: true }}>
//         {({ zoomIn, zoomOut, resetTransform }) => (
//           <>
//             <div style={{ display: "flex", justifyContent: "center", gap: "10px", padding: "10px" }}>
//               <button onClick={zoomIn}>+</button>
//               <button onClick={zoomOut}>-</button>
//               <button onClick={resetTransform}>Reset</button>
//             </div>
//             <TransformComponent wrapperStyle={{ width: "100%", height: "calc(100% - 52px)" }}>
//               <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
//                 <img src={src} alt="Super-resolved output" style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
//               </div>
//             </TransformComponent>
//           </>
//         )}
//       </TransformWrapper>
//     </div>
//   );
// };

// const ImageViewer = ({ imageData, fileType, file, detectionData, imageMetadata, overlayImage }) => {
//   const canvasRef = useRef(null);
//   const [leftReady, setLeftReady] = useState(false);
//   const [rightReady, setRightReady] = useState(false);
//   const [compositeImage, setCompositeImage] = useState(null);

//   const leftMapRef = useRef(null);
//   const rightMapRef = useRef(null);
//   const isSyncingRef = useRef(false);

//   const isSuperResolution = imageMetadata?.scale_factor !== undefined;

//   // Compose overlay + base image for non-TIFF images
//   useEffect(() => {
//     if (!imageData || !overlayImage || file?.type === "image/tiff") return;

//     const canvas = canvasRef.current;
//     if (!canvas) return;
//     const ctx = canvas.getContext("2d");
//     const baseImg = new Image();
//     const overlayImg = new Image();

//     baseImg.crossOrigin = "anonymous";
//     overlayImg.crossOrigin = "anonymous";

//     let baseLoaded = false;
//     let overlayLoaded = false;

//     const drawComposite = () => {
//       if (!baseLoaded || !overlayLoaded) return;

//       canvas.width = baseImg.width;
//       canvas.height = baseImg.height;

//       ctx.clearRect(0, 0, canvas.width, canvas.height);
//       ctx.drawImage(baseImg, 0, 0);
//       ctx.globalAlpha = 0.7;
//       ctx.drawImage(overlayImg, 0, 0, canvas.width, canvas.height);
//       ctx.globalAlpha = 1.0;

//       canvas.toBlob((blob) => {
//         if (blob) setCompositeImage(URL.createObjectURL(blob));
//       }, "image/png");
//     };

//     baseImg.onload = () => { baseLoaded = true; drawComposite(); };
//     overlayImg.onload = () => { overlayLoaded = true; drawComposite(); };
//     baseImg.src = imageData;
//     overlayImg.src = overlayImage;

//     return () => {
//       if (compositeImage) URL.revokeObjectURL(compositeImage);
//     };
//   }, [imageData, overlayImage, file]);

//   // Sync maps
//   useEffect(() => {
//     if (!leftReady || !rightReady) return;
//     const left = leftMapRef.current;
//     const right = rightMapRef.current;
//     if (!left || !right) return;

//     const syncFromLeft = () => {
//       if (isSyncingRef.current) return;
//       isSyncingRef.current = true;
//       right.setView(left.getCenter(), left.getZoom(), { animate: false });
//       requestAnimationFrame(() => (isSyncingRef.current = false));
//     };

//     const syncFromRight = () => {
//       if (isSyncingRef.current) return;
//       isSyncingRef.current = true;
//       left.setView(right.getCenter(), right.getZoom(), { animate: false });
//       requestAnimationFrame(() => (isSyncingRef.current = false));
//     };

//     left.on("move", syncFromLeft);
//     right.on("move", syncFromRight);

//     return () => {
//       left.off("move", syncFromLeft);
//       right.off("move", syncFromRight);
//     };
//   }, [leftReady, rightReady]);

//   // Determine what to display
//   const displayImage = compositeImage || overlayImage || imageData;

//   // Main render
//   return (
//     <div style={{ width: "100%", height: "90vh" }}>
//       {/* Hidden canvas for compositing */}
//       <canvas ref={canvasRef} style={{ display: "none" }} />

//       {/* TIFF detection mode */}
//       {file && file.type === "image/tiff" && !isSuperResolution ? (
//         <GeoTIFFMap tiffBlob={file} detectionData={detectionData} imageMetadata={imageMetadata} />
//       ) : isSuperResolution && overlayImage && imageMetadata?.bounds ? (
//         // Super-resolution side-by-side
//         <div style={{ width: "100%", height: "100%", display: "flex", gap: "10px" }}>
//           {/* Left: basemap + raw only */}
//           <div style={{ flex: 1, minWidth: 0, borderRadius: "8px", overflow: "hidden" }}>
//             <SuperResolutionMap
//               overlayUrl={null} // no predicted
//               originalTiffBlob={file && file.type === "image/tiff" ? file : null} // raw only
//               imageMetadata={imageMetadata}
//               onMapReady={(map) => { leftMapRef.current = map; setLeftReady(true); }}
//             />
//           </div>

//           {/* Right: basemap + predicted only */}
//           <div style={{ flex: 1, minWidth: 0, borderRadius: "8px", overflow: "hidden" }}>
//             <SuperResolutionMap
//               overlayUrl={overlayImage} // predicted only
//               originalTiffBlob={null} // disable raw
//               imageMetadata={imageMetadata}
//               onMapReady={(map) => { rightMapRef.current = map; setRightReady(true); }}
//             />
//           </div>
//         </div>
//       ) : (
//         // Regular image display
//         <TransformWrapper
//           initialScale={1}
//           initialPositionX={0}
//           initialPositionY={0}
//           options={{
//             limitToBounds: true,
//             minScale: 0.5,
//             maxScale: 3,
//             centerContent: true,
//             wheel: { step: 0.2 },
//             doubleClick: { step: 1 },
//             panning: { velocityDisabled: true },
//             zoomIn: { animation: true, animationTime: 500 },
//             zoomOut: { animation: true, animationTime: 500 },
//             reset: { animation: true, animationTime: 500 },
//           }}
//         >
//           {({ zoomIn, zoomOut, resetTransform }) => (
//             <div>
//               <div style={{ display: "flex", justifyContent: "center", marginBottom: "0.1rem", gap: "1rem" }}>
//                 <i onClick={zoomIn} className="fi fi-rr-zoom-in" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
//                 <i onClick={zoomOut} className="fi fi-rr-zoom-out" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
//                 <i onClick={resetTransform} className="fi fi-rr-rotate-right" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
//               </div>
//               <TransformComponent>
//                 <img style={{ maxHeight: "80vh" }} src={displayImage} alt="Satellite" loading="lazy" />
//               </TransformComponent>
//             </div>
//           )}
//         </TransformWrapper>
//       )}
//     </div>
//   );
// };

// export default ImageViewer;


/////////////////////GPT/////////////////////////
// import React, { useRef, useEffect, useState } from "react";
// import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
// import GeoTIFFMap from "./GeoTIFFMap";
// import SuperResolutionMap from "./SuperResolutionMap";

// const SRImageOnlyViewer = ({ src }) => {
//   if (!src) {
//     return (
//       <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#6B7280" }}>
//         No SR output image available.
//       </div>
//     );
//   }

//   return (
//     <div style={{ height: "100%", width: "100%", background: "#0b0f19" }}>
//       <TransformWrapper initialScale={1} minScale={0.5} maxScale={6} wheel={{ step: 0.2 }} doubleClick={{ step: 1 }} panning={{ velocityDisabled: true }}>
//         {({ zoomIn, zoomOut, resetTransform }) => (
//           <>
//             <div style={{ display: "flex", justifyContent: "center", gap: "10px", padding: "10px" }}>
//               <button onClick={zoomIn}>+</button>
//               <button onClick={zoomOut}>-</button>
//               <button onClick={resetTransform}>Reset</button>
//             </div>
//             <TransformComponent wrapperStyle={{ width: "100%", height: "calc(100% - 52px)" }}>
//               <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
//                 <img src={src} alt="Super-resolved output" style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
//               </div>
//             </TransformComponent>
//           </>
//         )}
//       </TransformWrapper>
//     </div>
//   );
// };

// const ImageViewer = ({ imageData, fileType, file, detectionData, imageMetadata, overlayImage }) => {
//   const canvasRef = useRef(null);
//   const [leftReady, setLeftReady] = useState(false);
//   const [rightReady, setRightReady] = useState(false);
//   const [compositeImage, setCompositeImage] = useState(null);

//   const leftMapRef = useRef(null);
//   const rightMapRef = useRef(null);
//   const isSyncingRef = useRef(false);

//   const isSuperResolution = imageMetadata?.scale_factor !== undefined;

//   // Compose overlay + base image for non-TIFF images
//   useEffect(() => {
//     if (!imageData || !overlayImage || file?.type === "image/tiff") return;

//     const canvas = canvasRef.current;
//     if (!canvas) return;
//     const ctx = canvas.getContext("2d");
//     const baseImg = new Image();
//     const overlayImg = new Image();

//     baseImg.crossOrigin = "anonymous";
//     overlayImg.crossOrigin = "anonymous";

//     let baseLoaded = false;
//     let overlayLoaded = false;

//     const drawComposite = () => {
//       if (!baseLoaded || !overlayLoaded) return;

//       canvas.width = baseImg.width;
//       canvas.height = baseImg.height;

//       ctx.clearRect(0, 0, canvas.width, canvas.height);
//       ctx.drawImage(baseImg, 0, 0);
//       ctx.globalAlpha = 0.7;
//       ctx.drawImage(overlayImg, 0, 0, canvas.width, canvas.height);
//       ctx.globalAlpha = 1.0;

//       canvas.toBlob((blob) => {
//         if (blob) setCompositeImage(URL.createObjectURL(blob));
//       }, "image/png");
//     };

//     baseImg.onload = () => { baseLoaded = true; drawComposite(); };
//     overlayImg.onload = () => { overlayLoaded = true; drawComposite(); };
//     baseImg.src = imageData;
//     overlayImg.src = overlayImage;

//     return () => {
//       if (compositeImage) URL.revokeObjectURL(compositeImage);
//     };
//   }, [imageData, overlayImage, file]);

//   // Sync maps
//   useEffect(() => {
//     if (!leftReady || !rightReady) return;

//     const left = leftMapRef.current;
//     const right = rightMapRef.current;
//     if (!left || !right) return;

//     const sync = (source, target) => {
//       if (isSyncingRef.current) return;
//       isSyncingRef.current = true;
//       const center = source.getCenter();
//       const zoom = source.getZoom();
//       target.setView(center, zoom, { animate: false });
//       requestAnimationFrame(() => { isSyncingRef.current = false; });
//     };

//     const leftMove = () => sync(left, right);
//     const rightMove = () => sync(right, left);

//     left.on("move zoom", leftMove);
//     right.on("move zoom", rightMove);

//     return () => {
//       left.off("move zoom", leftMove);
//       right.off("move zoom", rightMove);
//     };
//   }, [leftReady, rightReady]);

//   const displayImage = compositeImage || overlayImage || imageData;

//   return (
//     <div style={{ width: "100%", height: "90vh" }}>
//       <canvas ref={canvasRef} style={{ display: "none" }} />

//       {/* TIFF detection mode */}
//       {file && file.type === "image/tiff" && !isSuperResolution ? (
//         <GeoTIFFMap tiffBlob={file} detectionData={detectionData} imageMetadata={imageMetadata} />
//       ) : isSuperResolution && overlayImage && imageMetadata?.bounds ? (
//         <div style={{ width: "100%", height: "100%", display: "flex", gap: "10px" }}>
//           {/* Left: basemap + raw only */}
//           <div style={{ flex: 1, minWidth: 0, borderRadius: "8px", overflow: "hidden" }}>
//             <SuperResolutionMap
//               overlayUrl={null} // no predicted
//               originalTiffBlob={file && file.type === "image/tiff" ? file : null} // raw only
//               imageMetadata={imageMetadata}
//               onMapReady={(map) => { leftMapRef.current = map; setLeftReady(true); }}
//             />
//           </div>

//           {/* Right: basemap + predicted only */}
//           <div style={{ flex: 1, minWidth: 0, borderRadius: "8px", overflow: "hidden" }}>
//             <SuperResolutionMap
//               overlayUrl={overlayImage} // predicted only
//               originalTiffBlob={null} // disable raw
//               imageMetadata={imageMetadata}
//               onMapReady={(map) => { rightMapRef.current = map; setRightReady(true); }}
//             />
//           </div>
//         </div>
//       ) : (
//         // Regular image display
//         <TransformWrapper
//           initialScale={1}
//           initialPositionX={0}
//           initialPositionY={0}
//           options={{
//             limitToBounds: true,
//             minScale: 0.5,
//             maxScale: 3,
//             centerContent: true,
//             wheel: { step: 0.2 },
//             doubleClick: { step: 1 },
//             panning: { velocityDisabled: true },
//             zoomIn: { animation: true, animationTime: 500 },
//             zoomOut: { animation: true, animationTime: 500 },
//             reset: { animation: true, animationTime: 500 },
//           }}
//         >
//           {({ zoomIn, zoomOut, resetTransform }) => (
//             <div>
//               <div style={{ display: "flex", justifyContent: "center", marginBottom: "0.1rem", gap: "1rem" }}>
//                 <i onClick={zoomIn} className="fi fi-rr-zoom-in" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
//                 <i onClick={zoomOut} className="fi fi-rr-zoom-out" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
//                 <i onClick={resetTransform} className="fi fi-rr-rotate-right" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
//               </div>
//               <TransformComponent>
//                 <img style={{ maxHeight: "80vh" }} src={displayImage} alt="Satellite" loading="lazy" />
//               </TransformComponent>
//             </div>
//           )}
//         </TransformWrapper>
//       )}
//     </div>
//   );
// };

// export default ImageViewer;

///////////////// PLEXITY/////////////////////
import React, { useRef, useEffect, useState, useCallback } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import GeoTIFFMap from "./GeoTIFFMap";
import SuperResolutionMap from "./SuperResolutionMap";

const SRImageOnlyViewer = ({ src }) => {
  if (!src) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "#6B7280" }}>
        No SR output image available.
      </div>
    );
  }

  return (
    <div style={{ height: "100%", width: "100%", background: "#0b0f19" }}>
      <TransformWrapper initialScale={1} minScale={0.5} maxScale={6} wheel={{ step: 0.2 }} doubleClick={{ step: 1 }} panning={{ velocityDisabled: true }}>
        {({ zoomIn, zoomOut, resetTransform }) => (
          <>
            <div style={{ display: "flex", justifyContent: "center", gap: "10px", padding: "10px" }}>
              <button onClick={zoomIn}>+</button>
              <button onClick={zoomOut}>-</button>
              <button onClick={resetTransform}>Reset</button>
            </div>
            <TransformComponent wrapperStyle={{ width: "100%", height: "calc(100% - 52px)" }}>
              <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <img src={src} alt="Super-resolved output" style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }} />
              </div>
            </TransformComponent>
          </>
        )}
      </TransformWrapper>
    </div>
  );
};

const ImageViewer = ({ imageData, fileType, file, detectionData, imageMetadata, overlayImage }) => {
  const canvasRef = useRef(null);
  const [leftReady, setLeftReady] = useState(false);
  const [rightReady, setRightReady] = useState(false);
  const [compositeImage, setCompositeImage] = useState(null);

  const leftMapRef = useRef(null);
  const rightMapRef = useRef(null);
  const isSyncingRef = useRef(false);

  const isSuperResolution = imageMetadata?.scale_factor !== undefined;

  // ✅ BULLETPROOF SYNC FUNCTION - Always uses fresh refs
  const syncMaps = useCallback((sourceRef, targetRef) => {
    if (isSyncingRef.current) return;
    
    const sourceMap = sourceRef.current;
    const targetMap = targetRef.current;
    
    if (!sourceMap || !targetMap || sourceMap === targetMap) return;

    isSyncingRef.current = true;
    
    try {
      const center = sourceMap.getCenter();
      const zoom = sourceMap.getZoom();
      targetMap.setView(center, zoom, { 
        animate: false,
        duration: 0 
      });
    } catch (error) {
      console.warn("Map sync error:", error);
    } finally {
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 100);
    }
  }, []);

  // Compose overlay + base image for non-TIFF images
  useEffect(() => {
    if (!imageData || !overlayImage || file?.type === "image/tiff") return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const baseImg = new Image();
    const overlayImg = new Image();

    baseImg.crossOrigin = "anonymous";
    overlayImg.crossOrigin = "anonymous";

    let baseLoaded = false;
    let overlayLoaded = false;

    const drawComposite = () => {
      if (!baseLoaded || !overlayLoaded) return;

      canvas.width = baseImg.width;
      canvas.height = baseImg.height;

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(baseImg, 0, 0);
      ctx.globalAlpha = 0.7;
      ctx.drawImage(overlayImg, 0, 0, canvas.width, canvas.height);
      ctx.globalAlpha = 1.0;

      canvas.toBlob((blob) => {
        if (blob) setCompositeImage(URL.createObjectURL(blob));
      }, "image/png");
    };

    baseImg.onload = () => { baseLoaded = true; drawComposite(); };
    overlayImg.onload = () => { overlayLoaded = true; drawComposite(); };
    baseImg.src = imageData;
    overlayImg.src = overlayImage;

    return () => {
      if (compositeImage) URL.revokeObjectURL(compositeImage);
    };
  }, [imageData, overlayImage, file]);

  // ✅ LEFT MAP READY - Set up listeners
  useEffect(() => {
    if (!leftReady || !leftMapRef.current) return;

    console.log("🎯 Left map sync listeners attached");
    const map = leftMapRef.current;
    
    // Debounced sync to prevent spam
    let syncTimeout;
    const handleLeftMove = () => {
      clearTimeout(syncTimeout);
      syncTimeout = setTimeout(() => {
        syncMaps(leftMapRef, rightMapRef);
      }, 50);
    };

    map.on('moveend', handleLeftMove);
    map.on('zoomend', handleLeftMove);

    return () => {
      map.off('moveend', handleLeftMove);
      map.off('zoomend', handleLeftMove);
      if (syncTimeout) clearTimeout(syncTimeout);
    };
  }, [leftReady, syncMaps]);

  // ✅ RIGHT MAP READY - Set up listeners  
  useEffect(() => {
    if (!rightReady || !rightMapRef.current) return;

    console.log("🎯 Right map sync listeners attached");
    const map = rightMapRef.current;
    
    // Debounced sync to prevent spam
    let syncTimeout;
    const handleRightMove = () => {
      clearTimeout(syncTimeout);
      syncTimeout = setTimeout(() => {
        syncMaps(rightMapRef, leftMapRef);
      }, 50);
    };

    map.on('moveend', handleRightMove);
    map.on('zoomend', handleRightMove);

    return () => {
      map.off('moveend', handleRightMove);
      map.off('zoomend', handleRightMove);
      if (syncTimeout) clearTimeout(syncTimeout);
    };
  }, [rightReady, syncMaps]);

  // ✅ INITIAL SYNC when both maps are ready
  useEffect(() => {
    if (leftReady && rightReady && leftMapRef.current && rightMapRef.current) {
      console.log("🔗 Initial sync between maps");
      // Sync right to left initially
      syncMaps(leftMapRef, rightMapRef);
    }
  }, [leftReady, rightReady, syncMaps]);

  const displayImage = compositeImage || overlayImage || imageData;

  return (
    <div style={{ width: "100%", height: "90vh" }}>
      <canvas ref={canvasRef} style={{ display: "none" }} />

      {/* TIFF detection mode */}
      {file && file.type === "image/tiff" && !isSuperResolution ? (
        <GeoTIFFMap tiffBlob={file} detectionData={detectionData} imageMetadata={imageMetadata} />
      ) : isSuperResolution && overlayImage && imageMetadata?.bounds ? (
        <div style={{ width: "100%", height: "100%", display: "flex", gap: "10px" }}>
          {/* Left: basemap + raw only */}
          <div style={{ 
            flex: 1, 
            minWidth: 0, 
            borderRadius: "8px", 
            overflow: "hidden",
            border: "2px solid #10b981",
            position: "relative"
          }}>
            <div style={{position: "absolute", top: 5, left: 5, background: "rgba(0,0,0,0.7)", color: "white", padding: "5px", borderRadius: "4px", fontSize: "12px"}}>
              Raw Image
            </div>
            <SuperResolutionMap
              overlayUrl={null}
              originalTiffBlob={file && file.type === "image/tiff" ? file : null}
              imageMetadata={imageMetadata}
              onMapReady={(map) => { 
                leftMapRef.current = map; 
                console.log('✅ LEFT MAP READY:', map.getCenter());
                setLeftReady(true); 
              }}
            />
          </div>

          {/* Right: basemap + predicted only */}
          <div style={{ 
            flex: 1, 
            minWidth: 0, 
            borderRadius: "8px", 
            overflow: "hidden",
            border: "2px solid #3B82F6",
            position: "relative"
          }}>
            <div style={{position: "absolute", top: 5, left: 5, background: "rgba(0,0,0,0.7)", color: "white", padding: "5px", borderRadius: "4px", fontSize: "12px"}}>
              Super Resolution
            </div>
            <SuperResolutionMap
              overlayUrl={overlayImage}
              originalTiffBlob={null}
              imageMetadata={imageMetadata}
              onMapReady={(map) => { 
                rightMapRef.current = map; 
                console.log('✅ RIGHT MAP READY:', map.getCenter());
                setRightReady(true); 
              }}
            />
          </div>
        </div>
      ) : (
        // Regular image display
        <TransformWrapper
          initialScale={1}
          initialPositionX={0}
          initialPositionY={0}
          options={{
            limitToBounds: true,
            minScale: 0.5,
            maxScale: 3,
            centerContent: true,
            wheel: { step: 0.2 },
            doubleClick: { step: 1 },
            panning: { velocityDisabled: true },
            zoomIn: { animation: true, animationTime: 500 },
            zoomOut: { animation: true, animationTime: 500 },
            reset: { animation: true, animationTime: 500 },
          }}
        >
          {({ zoomIn, zoomOut, resetTransform }) => (
            <div>
              <div style={{ display: "flex", justifyContent: "center", marginBottom: "0.1rem", gap: "1rem" }}>
                <i onClick={zoomIn} className="fi fi-rr-zoom-in" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
                <i onClick={zoomOut} className="fi fi-rr-zoom-out" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
                <i onClick={resetTransform} className="fi fi-rr-rotate-right" style={{ fontSize: 18, color: "#3B82F6", cursor: "pointer" }}></i>
              </div>
              <TransformComponent>
                <img style={{ maxHeight: "80vh" }} src={displayImage} alt="Satellite" loading="lazy" />
              </TransformComponent>
            </div>
          )}
        </TransformWrapper>
      )}
    </div>
  );
};

export default ImageViewer;

