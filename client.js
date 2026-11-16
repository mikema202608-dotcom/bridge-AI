const element = id => document.getElementById(id);

async function getVideos() {
  const response = await fetch('/api/videos');
  if (!response.ok) throw new Error('课程加载失败，请刷新重试。');
  return response.json();
}

function courseRow(video) {
  const row = document.createElement('div');
  row.className = 'lesson';
  const label = document.createElement('strong');
  label.textContent = video.title;
  const link = document.createElement('a');
  link.className = 'button ghost';
  link.href = '/?v=' + encodeURIComponent(video.id);
  link.textContent = '观看';
  row.append(label, link);
  return row;
}

async function showCourses(admin) {
  const list = element('list');
  try {
    const videos = await getVideos();
    list.replaceChildren();
    for (const video of videos) {
      const row = courseRow(video);
      if (admin) {
        const button = document.createElement('button');
        button.className = 'danger';
        button.textContent = '删除';
        button.onclick = async () => {
          if (!confirm('确定删除这节课的视频？')) return;
          button.disabled = true;
          try {
            const response = await fetch('/api/videos/' + video.id, {method: 'DELETE'});
            if (!response.ok) throw new Error(await response.text());
            await showCourses(true);
          } catch (error) {
            element('status').textContent = error.message || '删除失败。';
            button.disabled = false;
          }
        };
        row.append(button);
      }
      list.append(row);
    }
    if (!videos.length) list.textContent = '课程准备中，视频上传后会出现在这里。';

    const id = new URLSearchParams(location.search).get('v');
    if (id && !admin) {
      const video = videos.find(course => course.id === id);
      const player = element('player');
      player.hidden = false;
      if (!video) {
        player.textContent = '这节课程暂时不可观看。';
        return;
      }
      const heading = document.createElement('h2');
      heading.textContent = video.title;
      const media = document.createElement('video');
      media.controls = true;
      media.playsInline = true;
      media.preload = 'metadata';
      media.src = '/api/videos/' + video.id;
      player.append(heading, media);
      player.scrollIntoView();
    }
  } catch (error) {
    list.textContent = error.message || '课程加载失败。';
  }
}

const upload = element('upload');
if (upload) {
  upload.addEventListener('submit', async event => {
    event.preventDefault();
    const file = element('file').files[0];
    const title = element('title').value.trim();
    const status = element('status');
    const button = upload.querySelector('button');
    if (!file || !title) return;
    if (file.size > 50 * 1024 * 1024) {
      status.textContent = '请选一个不超过 50 MB 的视频。';
      return;
    }
    button.disabled = true;
    status.textContent = '正在上传，请保持页面打开…';
    try {
      const response = await fetch('/api/videos', {
        method: 'POST',
        headers: {'Content-Type': file.type, 'X-Video-Title': encodeURIComponent(title)},
        body: file
      });
      if (!response.ok) throw new Error(await response.text());
      status.textContent = '上传成功，访客现在可以观看。';
      upload.reset();
      await showCourses(true);
    } catch (error) {
      status.textContent = error.message || '上传失败。';
    } finally {
      button.disabled = false;
    }
  });
}
if (element('list')) showCourses(Boolean(upload));
