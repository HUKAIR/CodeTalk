(function(root){
  const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
  // Closed-form damped spring: stable and independent of the number of display frames.
  function spring(s,target,dt,frequency=15,damping=.82){
    const displacement=s.x-target,wd=frequency*Math.sqrt(1-damping*damping);
    const decay=Math.exp(-damping*frequency*dt),a=displacement,b=(s.v+damping*frequency*displacement)/wd;
    const cos=Math.cos(wd*dt),sin=Math.sin(wd*dt),wave=a*cos+b*sin;
    return {x:target+decay*wave,v:decay*((-a*wd*sin+b*wd*cos)-damping*frequency*wave)};
  }
  function zoom(pan,anchor,before,after){return {x:anchor.x-(anchor.x-pan.x)*after/before,y:anchor.y-(anchor.y-pan.y)*after/before};}
  root.CommercialMotion={clamp,spring,zoom};
  if(typeof module!=='undefined')module.exports=root.CommercialMotion;
})(globalThis);
