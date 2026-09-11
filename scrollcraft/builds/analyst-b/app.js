/* Direction B only. All graphics are illustrative, with no model or live dataset. */
(() => {
  const root = document.documentElement;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const desktop = window.matchMedia('(min-width: 901px)');
  const motionButton = document.querySelector('#motion');
  const range = document.querySelector('#swing');
  const output = document.querySelector('#swing-value');
  let paused = media.matches;
  let context;
  let featureTrigger;
  let interacted = false;
  const chapters = [...document.querySelectorAll('.chapter')];
  const views = [...document.querySelectorAll('.bench-view')];
  const chapterLinks = [...document.querySelectorAll('[data-step]')];
  function updateDial(value) {
    range.value = value;
    output.value = `${Number(value) >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)} ${output.dataset.unit || 'pp'}`;
    document.querySelector('.small-rotor').style.transform = `rotate(${Number(value) * 24}deg)`;
  }
  range.addEventListener('input', () => { interacted = true; updateDial(range.value); });
  function visibleChapter(index) {
    chapters.forEach((el, i) => { el.inert = i !== index; });
    views.forEach((el, i) => { el.inert = i !== index; });
    chapterLinks.forEach((el, i) => el.setAttribute('aria-current', String(i === index)));
  }
  function setup() {
    context?.revert();
    featureTrigger = null;
    views.forEach(view => document.querySelector('.workbench').insertBefore(view, document.querySelector('.bench-footer')));
    root.classList.remove('animated', 'motion-static');
    chapters.concat(views).forEach(el => { el.inert = false; });
    motionButton.setAttribute('aria-pressed', String(paused));
    motionButton.textContent = paused
      ? (motionButton.dataset.resume || 'Resume motion')
      : (motionButton.dataset.pause || 'Pause motion');
    if (paused || !window.gsap || !window.ScrollTrigger || !desktop.matches) {
      root.classList.add('motion-static');
      views.forEach((view, index) => chapters[index].append(view));
      return;
    }
    root.classList.add('animated');
    gsap.registerPlugin(ScrollTrigger);
    context = gsap.context(() => {
      const hero = gsap.timeline({scrollTrigger:{trigger:'.hero',start:'top top',end:'+=780',pin:true,scrub:0.75,invalidateOnRefresh:true}});
      hero.to('.assembly',{rotateX:0,rotateY:0,rotateZ:0,x:8,scale:0.95,ease:'none'},0)
        .to('.back-plate',{x:68,y:-98,z:-110,ease:'none'},0)
        .to('.middle-plate',{x:34,y:-49,z:-55,ease:'none'},0)
        .to('.dial-rotor',{rotation:65,ease:'none'},0)
        .to('.mini-slider i',{left:'80%',ease:'none'},0)
        .to('.mini-slider span',{width:'80%',ease:'none'},0)
        .to('.hero-grid',{y:95,ease:'none'},0);
      gsap.fromTo('.manifesto h2 span',{opacity:.2},{opacity:1,stagger:.3,ease:'none',scrollTrigger:{trigger:'.manifesto',start:'top 80%',end:'bottom 65%',scrub:true}});
      gsap.set(chapters.slice(1),{autoAlpha:0,y:35});
      gsap.set(views.slice(1),{autoAlpha:0,y:70,scale:.92});
      visibleChapter(0);
      const dialState = {value:0};
      const sequence = gsap.timeline({scrollTrigger:{trigger:'.instruments',start:'top top',end:'+=2300',pin:true,scrub:.65,invalidateOnRefresh:true,onUpdate:self=>{
        const step = self.progress < .34 ? 0 : self.progress < .68 ? 1 : 2;
        visibleChapter(step);
        document.querySelector('.stage-progress i').style.transform = `scaleX(${Math.max(.05,self.progress)})`;
      }}});
      featureTrigger = sequence.scrollTrigger;
      sequence.to(dialState,{value:3.2,duration:1,ease:'none',onUpdate:()=>{if(!interacted)updateDial(dialState.value);}},0);
      sequence.to(chapters[0],{autoAlpha:0,y:-25,duration:.25},1)
        .to(views[0],{autoAlpha:0,y:-70,scale:1.06,duration:.35},1)
        .to(chapters[1],{autoAlpha:1,y:0,duration:.3},1.15)
        .to(views[1],{autoAlpha:1,y:0,scale:1,duration:.4},1.15)
        .fromTo('.source-node',{x:15},{x:0,stagger:.12,duration:.45},1.4)
        .to(chapters[1],{autoAlpha:0,y:-25,duration:.25},2.25)
        .to(views[1],{autoAlpha:0,y:-70,scale:1.06,duration:.35},2.25)
        .to(chapters[2],{autoAlpha:1,y:0,duration:.3},2.4)
        .to(views[2],{autoAlpha:1,y:0,scale:1,duration:.4},2.4)
        .fromTo('.file-row',{x:20,opacity:.35},{x:0,opacity:1,stagger:.1,duration:.4},2.65)
        .to({}, {duration:.35});
    });
    ScrollTrigger.refresh();
  }
  chapterLinks.forEach(link => link.addEventListener('click',event => {
    if (!featureTrigger) return;
    event.preventDefault();
    const positions = [.08,.47,.9];
    window.scrollTo({top:featureTrigger.start+(featureTrigger.end-featureTrigger.start)*positions[Number(link.dataset.step)],behavior:'smooth'});
  }));
  motionButton.addEventListener('click', () => {paused = !paused;setup();});
  media.addEventListener('change', () => {paused=media.matches;setup();});
  desktop.addEventListener('change',setup);
  document.fonts.ready.then(setup);
})();
