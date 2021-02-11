import numpy as np
import math
import random
import os
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
import itertools
from path import Path
from models import *
import yaml





def get_path(classes=40,sampled=True):
    #path=os.path.join('data','ModelNet40-1024')

    additianl = "-1024" if sampled else ""
    if classes == 40:
        return Path("data/ModelNet40"+additianl)
    return Path("data/ModelNet10"+additianl)


def default_transforms():
    return transforms.Compose([
                                PointSampler(1024),
                                Normalize(),
                                ToTensor()
                              ])


class PointSampler(object):
    def __init__(self, output_size):
        assert isinstance(output_size, int)
        self.output_size = output_size

    def triangle_area(self, pt1, pt2, pt3):
        side_a = np.linalg.norm(pt1 - pt2)
        side_b = np.linalg.norm(pt2 - pt3)
        side_c = np.linalg.norm(pt3 - pt1)
        s = 0.5 * (side_a + side_b + side_c)
        return max(s * (s - side_a) * (s - side_b) * (s - side_c), 0) ** 0.5

    def sample_point(self, pt1, pt2, pt3):
        # barycentric coordinates on a triangle
        # https://mathworld.wolfram.com/BarycentricCoordinates.html
        s, t = sorted([random.random(), random.random()])
        f = lambda i: s * pt1[i] + (t - s) * pt2[i] + (1 - t) * pt3[i]
        return (f(0), f(1), f(2))

    def __call__(self, mesh):
        verts, faces = mesh
        verts = np.array(verts)
        areas = np.zeros((len(faces)))

        for i in range(len(areas)):
            areas[i] = (self.triangle_area(verts[faces[i][0]],
                                           verts[faces[i][1]],
                                           verts[faces[i][2]]))

        sampled_faces = (random.choices(faces,
                                        weights=areas,
                                        cum_weights=None,
                                        k=self.output_size))

        sampled_points = np.zeros((self.output_size, 3))

        for i in range(len(sampled_faces)):
            sampled_points[i] = (self.sample_point(verts[sampled_faces[i][0]],
                                                   verts[sampled_faces[i][1]],
                                                   verts[sampled_faces[i][2]]))

        return sampled_points


class Normalize(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape) == 2

        norm_pointcloud = pointcloud - np.mean(pointcloud, axis=0)
        norm_pointcloud /= np.max(np.linalg.norm(norm_pointcloud, axis=1))

        return norm_pointcloud


class RandRotation_z(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape) == 2

        theta = random.random() * 2. * math.pi
        rot_matrix = np.array([[math.cos(theta), -math.sin(theta), 0],
                               [math.sin(theta), math.cos(theta), 0],
                               [0, 0, 1]])

        rot_pointcloud = rot_matrix.dot(pointcloud.T).T
        return rot_pointcloud


class RandomNoise(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape) == 2

        noise = np.random.normal(0, 0.02, (pointcloud.shape))

        noisy_pointcloud = pointcloud + noise
        return noisy_pointcloud
class ToTensor(object):
    def __call__(self, pointcloud):
        assert len(pointcloud.shape)==2

        return torch.from_numpy(pointcloud)
class PointCloudData(Dataset):
    def __init__(self, root_dir, valid=False, folder="train", transform=default_transforms()):
        self.root_dir = root_dir
        folders = [dir for dir in sorted(os.listdir(root_dir)) if os.path.isdir(root_dir/dir)]
        self.classes = {folder: i for i, folder in enumerate(folders)}
        self.transforms = transform if not valid else default_transforms()
        self.valid = valid
        self.files = []
        for category in self.classes.keys():
            new_dir = root_dir/Path(category)/folder
            for file in os.listdir(new_dir):
                if file.endswith('.off'):
                    sample = {}
                    sample['pcd_path'] = new_dir/file
                    sample['category'] = category
                    self.files.append(sample)

    def __len__(self):
        return len(self.files)

    def __preproc__(self, file):
        verts, faces = read_off(file)
        if self.transforms:
            pointcloud = self.transforms((verts, faces))
        return pointcloud

    def __getitem__(self, idx):
        pcd_path = self.files[idx]['pcd_path']
        category = self.files[idx]['category']
        with open(pcd_path, 'r') as f:
            pointcloud = self.__preproc__(f)
        return {'pointcloud': pointcloud,
                'category': self.classes[category]}

def read_off(file):
    if 'OFF' != file.readline().strip():
        raise ('Not a valid OFF header')
    n_verts, n_faces, __ = tuple([int(s) for s in file.readline().strip().split(' ')])
    verts = [[float(s) for s in file.readline().strip().split(' ')] for i_vert in range(n_verts)]
    faces = [[int(s) for s in file.readline().strip().split(' ')][1:] for i_face in range(n_faces)]
    return verts, faces




if __name__ == "__main__":
    #parameters and initilizations
    random.seed = 42
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    with open(os.path.join(os.getcwd(), 'config/config.yml'), 'r') as yml_file:
        config = yaml.load(yml_file)
        print('------------ config ------------')
        print(yaml.dump(config))
        NUM_CLASSES  = config['data']['num_classes']
        sampled_data = config['data']['sampled_data']
        TRAIN_BATCH  = config['model']['train_batch']
        TEST_BATCH   = config['model']['test_batch']
        EPOCHS       = config['model']['EPOCHS']
        SAMPLING_POINTS =config['data']['sampling_points']

    path = get_path(classes=NUM_CLASSES,sampled=sampled_data)
    folders = [dir for dir in sorted(os.listdir(path)) if os.path.isdir(path / dir)]
    classes = {folder: i for i, folder in enumerate(folders)}
    print(f"classes: {classes}")
    if sampled_data:
        import utils
        train_transforms = transforms.Compose([
            Normalize(),
            RandomNoise(),
        ])
        train_ds = utils.ModelNetDataset(path,train=True,transform=train_transforms)
        valid_ds = utils.ModelNetDataset(path, train=False, transform=train_transforms)
    else:
        train_transforms = transforms.Compose([
            PointSampler(SAMPLING_POINTS),
            Normalize(),
            RandRotation_z(),
            RandomNoise(),
            ToTensor()
        ])
        train_ds = PointCloudData(path, transform=train_transforms)
        valid_ds = PointCloudData(path, valid=True, folder='test')

    train_loader = DataLoader(dataset=train_ds, batch_size=TRAIN_BATCH, shuffle=True)
    valid_loader = DataLoader(dataset=valid_ds, batch_size=TEST_BATCH)


    pointnet = PointNet(train_loader, valid_loader,classes=NUM_CLASSES,sampled_data=sampled_data).to(device)
    print("---TRAINING---")
    pointnet.train_all(epochs=EPOCHS, with_val=True)
    """load best model from a file"""
    #pointnet.load_state_dict(torch.load('best_PointNet_model.pth'))
    """load best model from the atribute best_model (use when we train)"""
    pointnet.load_state_dict(pointnet.best_model)
    print("---TESTING---")
    val = pointnet.test_all()
    print('Test accuracy: %d %%' % val)

